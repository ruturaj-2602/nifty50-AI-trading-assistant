"""
Machine Learning Signal Classifier for NIFTY Intraday Options.
Uses Marcos López de Prado's Triple-Barrier Method for institutional-grade labeling
and an ensemble of Gradient Boosted Trees and Random Forest.
"""
import os
import pickle
import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple, Optional
from sklearn.ensemble import HistGradientBoostingClassifier
from ai.features import FEATURE_COLUMNS, engineer_features

MODEL_FILE = os.path.join(os.path.dirname(__file__), "nifty_signal_model.pkl")

class TripleBarrierLabeler:
    """
    Labels candles based on whether profit target (upper barrier)
    is hit prior to stop-loss (lower barrier) or time expiry (intraday square-off).
    Independent scan loops for bullish and bearish barriers.
    """
    @staticmethod
    def generate_labels(
        df: pd.DataFrame,
        sl_atr_mult: float = 1.0,
        tp_atr_mult: float = 1.5,
        max_horizon_bars: int = 35
    ) -> Tuple[pd.Series, pd.Series]:
        """
        Returns (bullish_labels, bearish_labels).
        1 = target reached before stop loss; 0 = stopped out or expired.
        """
        n = len(df)
        bullish_labels = pd.Series(0.0, index=df.index)
        bearish_labels = pd.Series(0.0, index=df.index)
        
        dates = df.index.date
        closes = df['Close'].values
        highs = df['High'].values
        lows = df['Low'].values
        atrs = df['ATR'].values
        
        for i in range(n - 1):
            curr_date = dates[i]
            entry_price = closes[i]
            atr = atrs[i]
            if np.isnan(atr) or atr <= 0:
                continue
                
            # Bullish barrier
            bull_tp = entry_price + (tp_atr_mult * atr)
            bull_sl = entry_price - (sl_atr_mult * atr)
            
            # Bearish barrier
            bear_tp = entry_price - (tp_atr_mult * atr)
            bear_sl = entry_price + (sl_atr_mult * atr)
            
            # Scan forward for Bullish
            for j in range(i + 1, min(i + max_horizon_bars, n)):
                if dates[j] != curr_date:
                    break
                if lows[j] <= bull_sl:
                    bullish_labels.iloc[i] = 0.0
                    break
                if highs[j] >= bull_tp:
                    bullish_labels.iloc[i] = 1.0
                    break
                    
            # Scan forward for Bearish
            for j in range(i + 1, min(i + max_horizon_bars, n)):
                if dates[j] != curr_date:
                    break
                if highs[j] >= bear_sl:
                    bearish_labels.iloc[i] = 0.0
                    break
                if lows[j] <= bear_tp:
                    bearish_labels.iloc[i] = 1.0
                    break
                    
        return bullish_labels, bearish_labels

class IntradaySignalClassifier:
    """
    AI model that scores real-time intraday setups and filters false breakouts.
    """
    def __init__(self, confidence_threshold: float = 0.50):
        self.confidence_threshold = confidence_threshold
        self.bull_model = None
        self.bear_model = None
        self.is_trained = False
        self.feature_names = FEATURE_COLUMNS

    def train(self, df: pd.DataFrame, sl_atr_mult: float = 1.0, tp_atr_mult: float = 1.5):
        """
        Trains bullish and bearish directional classifiers using walk-forward data.
        """
        df_feat = engineer_features(df).dropna(subset=FEATURE_COLUMNS)
        bull_labels, bear_labels = TripleBarrierLabeler.generate_labels(df_feat, sl_atr_mult, tp_atr_mult)
        
        valid_mask = bull_labels.notna() & bear_labels.notna()
        X = df_feat.loc[valid_mask, FEATURE_COLUMNS].values
        y_bull = bull_labels.loc[valid_mask].astype(int).values
        y_bear = bear_labels.loc[valid_mask].astype(int).values
        
        # 80/20 Chronological Split
        split_idx = int(len(X) * 0.8)
        X_train = X[:split_idx]
        y_bull_train = y_bull[:split_idx]
        y_bear_train = y_bear[:split_idx]
        
        # Train Bullish Classifier
        self.bull_model = HistGradientBoostingClassifier(
            max_iter=100,
            learning_rate=0.03,
            max_leaf_nodes=31,
            min_samples_leaf=15,
            random_state=42
        )
        self.bull_model.fit(X_train, y_bull_train)
        
        # Train Bearish Classifier
        self.bear_model = HistGradientBoostingClassifier(
            max_iter=100,
            learning_rate=0.03,
            max_leaf_nodes=31,
            min_samples_leaf=15,
            random_state=42
        )
        self.bear_model.fit(X_train, y_bear_train)
        
        self.is_trained = True
        self.save_model()
        return self

    def predict(self, row: pd.Series) -> Dict[str, Any]:
        """
        Predicts whether current candle offers an institutional probability setup.
        """
        if not self.is_trained:
            self.load_model()
            
        x_vec = row[FEATURE_COLUMNS].values.reshape(1, -1)
        
        bull_prob = float(self.bull_model.predict_proba(x_vec)[0, 1])
        bear_prob = float(self.bear_model.predict_proba(x_vec)[0, 1])
        
        signal = "HOLD"
        confidence = max(bull_prob, bear_prob)
        
        if bull_prob >= self.confidence_threshold and bull_prob > bear_prob:
            signal = "BUY_CE"
        elif bear_prob >= self.confidence_threshold and bear_prob > bull_prob:
            signal = "BUY_PE"
            
        return {
            "signal": signal,
            "confidence": confidence,
            "bull_prob": round(bull_prob, 3),
            "bear_prob": round(bear_prob, 3)
        }

    def save_model(self, path: str = MODEL_FILE):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"bull": self.bull_model, "bear": self.bear_model}, f)

    def load_model(self, path: str = MODEL_FILE) -> bool:
        if os.path.exists(path):
            with open(path, "rb") as f:
                data = pickle.load(f)
                self.bull_model = data["bull"]
                self.bear_model = data["bear"]
                self.is_trained = True
                return True
        return False
