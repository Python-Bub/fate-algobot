import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from config import TICKERS, MODEL_DIR
from feature_engineering import build_features

def train_meta_model():
    """
    Loads base models, builds meta‐features, trains & saves a meta‐learner.
    """
    meta_X, meta_y = [], []

    for ticker in TICKERS:
        df = build_features(ticker, start="2023-01-01", end=None)
        df["target"] = (df["ret"].shift(-1) > 0).astype(int)
        df.dropna(inplace=True)

        feats = ["close","rsi","vol_ch","sentiment"]
        X_base = df[feats].values
        y       = df["target"].values

        # load scalers & models
        scaler = joblib.load(f"{MODEL_DIR}/{ticker}_scaler.pkl")
        Xs     = scaler.transform(X_base)

        preds = []
        for m in ["rf","xgb","lgb"]:
            mdl = joblib.load(f"{MODEL_DIR}/{ticker}_{m}.pkl")
            preds.append(mdl.predict_proba(Xs)[:,1])

        # stack predictions
        meta_X.append(np.column_stack(preds))
        meta_y.append(y)

    X_meta = np.vstack(meta_X)
    y_meta = np.hstack(meta_y)

    meta_model = RandomForestClassifier(n_estimators=100)
    meta_model.fit(X_meta, y_meta)
    joblib.dump(meta_model, f"{MODEL_DIR}/meta_model.pkl")
    print("Meta‐model trained and saved.")
