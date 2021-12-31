import random
import Progetto_Scripts.Generate_Programs as GP
import pandas as pd
import string
import cx_Oracle as cx
import datetime


def createReservations():
    dict_users, dict_cinemas, dict_auditoria, dict_seats, dict_programming  = GP.createPrograms()
    dict = {}
    dict['id_reservation'] = []                                                         # Definizione schema Reservations
    dict['programming_id'] = []
    dict['position_number'] = []
    dict['auditorium_number'] = []
    dict['cinema_id'] = []
    dict['user_email'] = []
    dict['paid'] = []
    dict['payment_method'] = []

    reservations = {}
    reservations['cinema_id'] = []
    reservations['auditorium_number'] = []
    reservations['id_programming'] = []
    reservations['max_seats'] = []
    reservations['reserved_seats'] = []
    for i in range(len(dict_programming['id_programming'])):                                            # Per ogni programmazione
        for j in range(len(dict_auditoria['cinema_id'])):                                               # .. e per ogni auditorium
            if (dict_auditoria['cinema_id'][j] == dict_programming['cinema_id'][i] and                     # legato a quel determinato
                    dict_auditoria['auditorium_number'][j] == dict_programming['auditorium_number'][i]):    # programma
                reservations['cinema_id'].append(dict_auditoria['cinema_id'][j])
                reservations['auditorium_number'].append(dict_auditoria['auditorium_number'][j])            # Creata una sessione
                reservations['id_programming'].append(dict_programming['id_programming'][i])                # di prenotazione
                reservations['max_seats'].append(dict_auditoria['nr_seats'][j])
                reservations['reserved_seats'].append({})

    p_reservation = 0.8                                                                 # Ogni utente ha la prob di 80%
                                                                                        # di prenotare in una delle poss. sessioni

    density_companionship = [0,20,35,55,80,75,60,45,30,17,16,14,13,13,12,11,9,6,5,4,3]    # <- prob di prenotare per altre x persone
    count = 0
    for user in dict_users['email']*10:                                        # 10 possibilità di andare al cinema per ogni utente
        if random.random()<p_reservation:
            p = random.random()
            total = 1
            for i in range(len(density_companionship)):
                if p<sum(density_companionship[:i])/sum(density_companionship):
                    total = i
                    break

            random_reservation = random.randrange(0, len(reservations['cinema_id']))            # Riempimento delle sale
            tot_length = 0                                                                      # con attenzione all'overflow
            for key in reservations['reserved_seats'][random_reservation].keys():
                tot_length += len(reservations['reserved_seats'][random_reservation][key])
            while not reservations['max_seats'][random_reservation] - tot_length - total>0:
                random_reservation = random.randrange(0, len(reservations['cinema_id']))

            tot_length = 0
            for key in reservations['reserved_seats'][random_reservation].keys():
                tot_length += len(reservations['reserved_seats'][random_reservation][key])

                                                                                                # Creazione tabella reservations

            reservations['reserved_seats'][random_reservation][user] = [i for i in range(tot_length, tot_length + total)]
            for j in range(tot_length, tot_length + total):
                count += 1
                dict['id_reservation'].append(count)
                dict['programming_id'].append(reservations['id_programming'][random_reservation])
                dict['position_number'].append(j+1)
                dict['cinema_id'].append(reservations['cinema_id'][random_reservation])
                dict['auditorium_number'].append(reservations['auditorium_number'][random_reservation])
                dict['user_email'].append(user)
                dict['paid'].append(random.choice([0,1,1,1,1]))
                dict['payment_method'].append(random.choice(['Credit card','Bank transfer','Business','Cash',
                                                             'Debit card','Check','PayPal','Visa', 'Electron Visa']))


    return dict_users, dict_cinemas, dict_auditoria, dict_seats, dict_programming, dict