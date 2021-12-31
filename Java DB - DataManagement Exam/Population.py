import Progetto_Scripts.Connection as C
import cx_Oracle as cx
import Progetto_Scripts.Generate_Reservations as GR
import pandas as pd
import numpy as np

def populateDB(for_real):                                                                       # Popolamento effettivo del DB
    '''dict_users, dict_cinemas, dict_auditoria, dict_seats, dict_programming, dict_reservations'''
    dicts = GR.createReservations()
    dataframes = []
    for index in range(len(dicts)):
        dataframes.append(pd.DataFrame(dicts[index]))                                           # Creazione dataframe
        print(dataframes[index].head(20))
        print('')
    #if for_real: C.dftodb(connection, 'reservations', df)                                       # Invio al DB sul server



def main():
    connection = cx.connect("C##PROGETTISTA", "123456", "26.158.138.90/orclglobal", encoding="UTF-8", nencoding="UTF-8")
    cursor = connection.cursor()
    #populateDB(False)
    result1 = cursor.execute('''SELECT
                                    films.published_year,
                                    actors.actor_name
                                FROM
                                    films
                                    INNER JOIN cast ON films.id_film = cast.film_id
                                    INNER JOIN actors ON cast.actor_id = actors.id_actor
                                WHERE
                                    films.title = 'Batman'
                                    AND films.duration_minutes > 55
                                ORDER BY
                                    films.published_year,
                                    actors.actor_name''')

    result = cursor.execute(''' SELECT
                                    COUNT(users.email) AS "Reservations_Count"
                                FROM
                                    programming
                                INNER JOIN reservations ON programming.id_programming = reservations.programming_id
                                INNER JOIN users ON reservations.user_email = users.email
                                GROUP BY
                                    users.first_name,
                                    programming.id_programming''')
    date = []
    for row in result:
        date.append(row[0])

    import matplotlib.pyplot as plt

    plot = plt.hist(date, bins = range(30))
    plt.show()


main()