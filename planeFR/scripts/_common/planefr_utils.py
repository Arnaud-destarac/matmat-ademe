"""
Helpers shared by several PlaneFR pipeline scripts.
"""

import pandas as pd


def make_pickle_portable(df):
    """Casts the index/column levels and the text columns to dtype 'object'
    before pickling. The pickle format of the 'string' dtypes (StringDtype,
    pyarrow backend included) is not stable from one pandas version to
    another: a pickle written with pandas >= 3.0 (where text is StringDtype by
    default) cannot be read back by the pandas 2.x used by matmat-ademe
    (.venv), whatever the Python interpreter used to run the script.

    Same treatment as PickleFormat._make_pickle_portable in
    src/matmat/utils/formats/core.py, for the scripts that write pickles
    without going through MatMat."""

    def sanitize_index(index):
        if isinstance(index, pd.MultiIndex):
            if any(isinstance(level.dtype, pd.StringDtype) for level in index.levels):
                return index.set_levels(
                    [
                        level.astype(object) if isinstance(level.dtype, pd.StringDtype) else level
                        for level in index.levels
                    ]
                )
            return index
        if isinstance(index.dtype, pd.StringDtype):
            return index.astype(object)
        return index

    df = df.copy()
    df.index = sanitize_index(df.index)
    df.columns = sanitize_index(df.columns)
    string_cols = [c for c in df.columns if isinstance(df[c].dtype, pd.StringDtype)]
    if string_cols:
        df[string_cols] = df[string_cols].astype(object)
    return df
