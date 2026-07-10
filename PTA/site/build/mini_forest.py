"""
A minimal, dependency-free (numpy only) Random Forest classifier.
Used because scikit-learn cannot be installed in this build sandbox (no
outbound network access for pip). Mirrors the intent of the notebook's
RandomForestClassifier(class_weight='balanced_subsample') closely enough
for an explainable, reproducible next-day fire-risk model:
 - bootstrap sample per tree, rebalanced across classes ("balanced_subsample")
 - random feature subset per split ("sqrt" of feature count)
 - CART-style greedy splits on Gini impurity, using quantile candidate thresholds
 - leaves store class probability vectors; forest averages them
 - Gini-based feature importance, accumulated across all trees/splits
"""
import numpy as np


class _Node:
    __slots__ = ('feature', 'threshold', 'left', 'right', 'proba', 'n')

    def __init__(self):
        self.feature = None
        self.threshold = None
        self.left = None
        self.right = None
        self.proba = None
        self.n = 0


def _gini(counts):
    n = counts.sum()
    if n == 0:
        return 0.0
    p = counts / n
    return 1.0 - np.sum(p * p)


class MiniForest:
    def __init__(self, n_estimators=30, max_depth=6, min_leaf=25,
                 n_quantiles=8, max_features='sqrt', bootstrap_size=6000,
                 random_state=42):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_leaf = min_leaf
        self.n_quantiles = n_quantiles
        self.max_features = max_features
        self.bootstrap_size = bootstrap_size
        self.random_state = random_state
        self.trees_ = []
        self.classes_ = None
        self.feature_importances_ = None
        self.n_features_ = None

    def fit(self, X, y, feature_names=None):
        rng = np.random.default_rng(self.random_state)
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y)
        self.classes_, y_idx = np.unique(y, return_inverse=True)
        n_classes = len(self.classes_)
        n_samples, n_features = X.shape
        self.n_features_ = n_features
        self.feature_names_ = feature_names or [f'f{i}' for i in range(n_features)]
        if self.max_features == 'sqrt':
            mtry = max(1, int(np.sqrt(n_features)))
        else:
            mtry = n_features

        by_class = [np.where(y_idx == c)[0] for c in range(n_classes)]
        importances = np.zeros(n_features)

        for t in range(self.n_estimators):
            # balanced_subsample-style bootstrap: equal draws per class
            per_class_n = max(1, self.bootstrap_size // n_classes)
            idx_parts = []
            for c in range(n_classes):
                pool = by_class[c]
                if len(pool) == 0:
                    continue
                draw = rng.choice(pool, size=per_class_n, replace=True)
                idx_parts.append(draw)
            boot_idx = np.concatenate(idx_parts)
            rng.shuffle(boot_idx)
            Xb, yb = X[boot_idx], y_idx[boot_idx]

            tree = self._build_node(Xb, yb, n_classes, depth=0, rng=rng,
                                     mtry=mtry, importances=importances)
            self.trees_.append(tree)

        total = importances.sum()
        self.feature_importances_ = importances / total if total > 0 else importances

    def _build_node(self, X, y, n_classes, depth, rng, mtry, importances):
        node = _Node()
        node.n = len(y)
        counts = np.bincount(y, minlength=n_classes).astype(float)
        node.proba = counts / counts.sum() if counts.sum() > 0 else np.ones(n_classes) / n_classes

        if depth >= self.max_depth or node.n < 2 * self.min_leaf or counts.max() == counts.sum():
            return node

        n_features = X.shape[1]
        feat_candidates = rng.choice(n_features, size=min(mtry, n_features), replace=False)
        parent_gini = _gini(counts)

        best_gain = 0.0
        best_feat, best_thresh = None, None
        best_left_mask = None

        for feat in feat_candidates:
            col = X[:, feat]
            finite = np.isfinite(col)
            if finite.sum() < 2 * self.min_leaf:
                continue
            qs = np.unique(np.quantile(col[finite], np.linspace(0.1, 0.9, self.n_quantiles)))
            for thresh in qs:
                left_mask = col <= thresh
                n_left = left_mask.sum()
                n_right = node.n - n_left
                if n_left < self.min_leaf or n_right < self.min_leaf:
                    continue
                left_counts = np.bincount(y[left_mask], minlength=n_classes).astype(float)
                right_counts = counts - left_counts
                gini_left = _gini(left_counts)
                gini_right = _gini(right_counts)
                weighted = (n_left * gini_left + n_right * gini_right) / node.n
                gain = parent_gini - weighted
                if gain > best_gain:
                    best_gain = gain
                    best_feat, best_thresh = feat, thresh
                    best_left_mask = left_mask

        if best_feat is None or best_gain <= 1e-9:
            return node

        importances[best_feat] += best_gain * node.n
        node.feature = best_feat
        node.threshold = best_thresh
        node.left = self._build_node(X[best_left_mask], y[best_left_mask], n_classes,
                                      depth + 1, rng, mtry, importances)
        node.right = self._build_node(X[~best_left_mask], y[~best_left_mask], n_classes,
                                       depth + 1, rng, mtry, importances)
        return node

    def _predict_one_tree(self, tree, X):
        n = X.shape[0]
        n_classes = len(self.classes_)
        out = np.zeros((n, n_classes))
        self._traverse(tree, X, np.arange(n), out)
        return out

    def _traverse(self, node, X, idx, out):
        if node.feature is None:
            out[idx] = node.proba
            return
        col = X[idx, node.feature]
        col = np.where(np.isfinite(col), col, np.nanmedian(col[np.isfinite(col)]) if np.isfinite(col).any() else 0)
        go_left = col <= node.threshold
        if go_left.any():
            self._traverse(node.left, X, idx[go_left], out)
        if (~go_left).any():
            self._traverse(node.right, X, idx[~go_left], out)

    def predict_proba(self, X):
        X = np.asarray(X, dtype=np.float64)
        n_classes = len(self.classes_)
        acc = np.zeros((X.shape[0], n_classes))
        for tree in self.trees_:
            acc += self._predict_one_tree(tree, X)
        return acc / len(self.trees_)

    def predict(self, X):
        proba = self.predict_proba(X)
        return self.classes_[np.argmax(proba, axis=1)]
