import random
import Progetto_Scripts.Generate_Root as GR
import pandas as pd
import string
import cx_Oracle as cx
import datetime

def reshapeUsers():                                                             # Ultime modifiche alla tabella users
    dict_users_ = GR.createRoot(0)
    dict_cinemas = GR.createRoot(1)                                                       # i 4 dizionari generati con la funzione
    dict_auditotia = GR.createRoot(2)                                                     #     createRoot()
    dict_seats = GR.createRoot(3)
    dict_users_['password'] = []                                                        # Aggiunta di : password
    dict_users_['favourite_cinema'] = []                                                #               cinema preferito
    dict_users_['birth_date'] = []                                                      #               anno nascita
    for i in range(len(dict_users_['email'])):
        password = ''
        for j in range(random.randrange(8, 15)):
            password += random.choice(string.ascii_letters)

        dict_users_['password'].append(password)
        dict_users_['favourite_cinema'].append(random.choice(dict_cinemas['id_cinema']))
        dict_users_['birth_date'].append(datetime.date(random.randrange(1950, 2006),
                                                       random.randrange(1, 13), random.randrange(1, 29)))

    indexes = []
    for i in range(len(dict_users_['email'])):                                              # Eliminazione di più unità aventi
        if not dict_users_['email'][:i].__contains__(dict_users_['email'][i]):              # stessa email (chiave primaria)
            indexes.append(i)

    dict_users = {}                                                                         # Ordinamento delle tuple
    dict_users['email']=[]                                                                  # pronte per essere iniettate
    dict_users['password']=[]
    dict_users['first_name']=[]
    dict_users['last_name']=[]
    dict_users['favourite_cinema']=[]
    dict_users['birth_date']=[]
    dict_users['address']=[]
    dict_users['state']=[]
    dict_users['city']=[]
    dict_users['cap']=[]
    dict_users['telephone']=[]
    dict_users['cellphone']=[]

    for i in range(len(dict_users_['email'])):
        if indexes.__contains__(i):
            dict_users['email'].append(dict_users_['email'][i])
            dict_users['first_name'].append(dict_users_['first_name'][i])
            dict_users['last_name'].append(dict_users_['last_name'][i])
            dict_users['password'].append(dict_users_['password'][i])
            dict_users['favourite_cinema'].append(dict_users_['favourite_cinema'][i])
            dict_users['birth_date'].append(dict_users_['birth_date'][i])
            dict_users['address'].append(dict_users_['address'][i])
            dict_users['state'].append(dict_users_['state'][i])
            dict_users['city'].append(dict_users_['city'][i])
            dict_users['cap'].append(dict_users_['postal'][i])
            dict_users['telephone'].append(dict_users_['phone1'][i])
            dict_users['cellphone'].append(dict_users_['phone2'][i])

    return dict_users, dict_cinemas, dict_auditotia, dict_seats

def createPrograms():                                                                       # Creazione programs
    connection = cx.connect("C##PROGETTISTA", "123456", "26.158.138.90/orclglobal",         # Connetto..
                            encoding="UTF-8", nencoding="UTF-8")
    cursor = connection.cursor()
    result1 = cursor.execute("SELECT id_film, duration_minutes FROM films where"            # Utilizzo solo i film di recente 
                             " published_year > 2010 and duration_minutes > 90")            # produzione (lungometraggi)
    id_film = []
    film_duration = []                                                                   # Copio tutte le informazioni rinvenute
    id_cinema_film = []                                                                  #                       *
    opening_time_film = []
    closing_time_film = []
    nr_auditoria = []

    for row in result1:                                                                               #          *
        id_film.append(int(row[0]))
        film_duration.append(int(row[1]))
    result2 = cursor.execute("SELECT id_cinema, opening_time, closing_time, nr_auditoria FROM cinemas")
    for row in result1:
        id_cinema_film.append(int(row[0]))
        opening_time_film.append(datetime.time(int(int(row[1])/100), abs(int(row[1]) - int(int(row[1])/100)*100), 0))
        closing_time_film.append(datetime.time(int(int(row[2])/100), abs(int(row[2]) - int(int(row[2])/100)*100), 0))
        nr_auditoria.append(int(row[3]))
    import time
    act_time = time.time()

    dict = {}
    dict['id_programming'] = []                                                               # Creazione dello schema
    dict['film_id'] = []
    dict['cinema_id'] = []
    dict['auditorium_number'] = []
    dict['programming_time'] = []
    dict['price'] = []
    dict['screening_time_minutes'] = []
    count_id = 0

    for cinema in range(len(id_cinema_film)):                                                   # Per ogni cinema
        for auditorium in range(nr_auditoria[cinema]):                                          # .. per ogni auditorium
            for i in range(15):                                                                     # dal 1 al 15 gennaio 2020
                act_time = opening_time_film[cinema].hour * 60 + opening_time_film[cinema].minute       # Traccio orari di apertura
                clos_time = closing_time_film[cinema].hour * 60 + closing_time_film[cinema].minute      # e chiusura
                if closing_time_film[cinema].hour <4: clos_time += 24*60
                prev_choice = -1
                choice = -1

                while act_time < clos_time:                                                         # Popolo la programmazione giornaliera
                    while choice == prev_choice:                                                    # fin tanto che la durata complessiva
                        choice = random.choice(range(len(id_film)))                                 # rientri negli orari
                    prev_choice = choice

                    out_time = act_time
                    if act_time >= 24*60: out_time -= 24*60
                    try: out_time = datetime.time(int(out_time/60), int((out_time/60)%(int(out_time/60))*60))
                    except Exception as e: out_time = datetime.time(0,0)
                    act_time += film_duration[choice]
                    if act_time < clos_time:
                        count_id += 1
                        dict['id_programming'].append(count_id)
                        dict['film_id'].append(id_film[choice])
                        dict['cinema_id'].append(id_cinema_film[cinema])
                        dict['auditorium_number'].append(auditorium+1)
                        dict['programming_time'].append(datetime.datetime(
                            year=2020,month=1,day=i+1,hour=out_time.hour, minute=out_time.minute))
                        dict['price'].append(random.randrange(5,12) + random.choice([0.0, 0.5]))        # Random price ( da 5 a 12.50)
                        dict['screening_time_minutes'].append(film_duration[choice])

    reshaped_users = reshapeUsers()
    return reshaped_users[0],reshaped_users[1],reshaped_users[2],reshaped_users[3], dict

