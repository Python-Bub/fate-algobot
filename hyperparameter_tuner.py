import optuna
from sklearn.model_selection import cross_val_score

def optimize_model(model_cls, X, y, param_space, n_trials=30, cv=3):
    """
    Automated hyperparameter tuning with Optuna.

    Args:
        model_cls:     scikit-learn estimator class (e.g. RandomForestClassifier)
        X, y:          Training data and labels
        param_space:   Dict of {param: (type, *args)},
                       e.g. {"n_estimators": ("int", 50, 300)}
        n_trials:      Number of Optuna trials
        cv:            Cross-validation folds

    Returns:
        best_params:   Dict of best hyperparameters
        best_value:    Best CV score achieved
    """
    def objective(trial):
        params = {}
        for name, cfg in param_space.items():
            t, *args = cfg
            if t == "int":
                params[name] = trial.suggest_int(name, *args)
            elif t == "float":
                params[name] = trial.suggest_float(name, *args)
            elif t == "categorical":
                params[name] = trial.suggest_categorical(name, args[0])
        model = model_cls(**params)
        score = cross_val_score(model, X, y, cv=cv, scoring="accuracy").mean()
        return score

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials)
    return study.best_params, study.best_value
