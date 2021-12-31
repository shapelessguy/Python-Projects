import pandas as pd
import cx_Oracle as cx


def dftodb(connection: cx.Connection, tableName: str, df: pd.DataFrame):
    """
    Inject a pandas dataframe to a certain table within an Oracle database.

    The column names MUST be the same used by the table attributes in the Oracle database.
    """

    cursor = connection.cursor()

    # SQL statement
    sql = "INSERT INTO {0} ({1}) VALUES (:{2})".format(
        tableName,
        ', '.join(df.columns),
        ', :'.join(list(map(str, range(1, len(df.columns) + 1))))
    )
    print("SQL:\n", sql)
    # Rows to inject as a list of lists
    rows = []
    for row in df.values:
        rows.append([None if pd.isnull(value) else value for value in row])
    print("First row:\n", rows[0])
    # Injection
    cursor.executemany(sql, rows)
    # Commit
    connection.commit()

    cursor.close()
    return
