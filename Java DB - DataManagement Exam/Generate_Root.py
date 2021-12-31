import random
import Progetto_Scripts.Generate_Users as GU                                                #Importo classe Generate_Users
import pandas as pd
import numpy as np

stolen_identities = []
class Tree:                                                                                   # Definizione classe albero
    def __init__(self, left = None, right = None, level = 0, dict = None,
                 random_gen = False, position = ['UniCinema'], attributes = {}):

        self.level = level                                                     # Ogni ramo è caratterizzato da un livello
        self.identity = -1
        self.attributes = attributes                                            # Ogni livello da specifici attributi

        self.all_child = []
        if level==0:
            self.all_child = [i for i in range(0, 10)]                              # Verranno creati 10 cinema

        if level==1:
            self.all_child = [i for i in range(0, attributes['nr_auditoria'])]       # Per ogni cinema, un numero di auditorium
                                                                                     # specificati negli attributi del cinema padre
        if level==2:
            self.all_child = [i for i in range(0, attributes['nr_seats'])]           # Per ogni auditorium, un numero di posti
                                                                                     # specificati negli attributi dell'auditorium padre

        self.position = position                                       # Traccia la posizione all'interno del tree degli elementi


        if (self.level == 0):                                                           #Per i cinema..
            cities = []
            stolen_attributes = {}

            for i in range(int(len(self.all_child))):                                   # Rubo 10 identità dal dataset users
                ok = False
                while not ok:
                    random_city = random.choice(dict['city'])                           # .. che abitano in città diverse
                    if not cities.__contains__(random_city):
                        cities.append(random_city)
                        ok = True

            for city in cities:                                                         # Tengo traccia delle identità rubate
                for i in range(len(dict['city'])):                                      # affinchè non compaiano nel db come utenti
                    if dict['city'][i] == city:
                        stolen_identities.append(i)
                        stolen_attributes[city] = []
                        for key in dict.keys():
                            stolen_attributes[city].append(dict[key][i])




        if random_gen and level<3:                                               #Genero gli attributi per ciascun elemento
            for i in range(len(self.all_child)):
                new_position = position[:]
                new_attributes = {}
                if self.level == 0:
                    new_attributes['id_cinema'] = i
                    new_attributes['opening_time'] = \
                        random.choice([8,9,10,11,12])*100 + random.choice(range(0,56, 5))
                    new_attributes['closing_time'] = \
                        random.choice([20,21,22,23,0,1])*100 + random.choice(range(0,56, 5))
                    new_attributes['rating'] = int((random.random()*7.99+2)*10)/10
                    new_attributes['nr_auditoria'] = random.randrange(2, 15)
                    new_attributes['state'] = stolen_attributes[cities[i]][4]
                    new_attributes['city'] = stolen_attributes[cities[i]][3]
                    new_attributes['address'] = stolen_attributes[cities[i]][2]
                    new_attributes['telephone'] = stolen_attributes[cities[i]][6]
                if self.level == 1:
                    dim = random.randint(10,30)
                    new_attributes['auditorium_number'] = i+1
                    new_attributes['cinema_id'] = attributes['id_cinema']
                    new_attributes['nr_seats'] = random.randrange(dim*6, dim*12)
                    new_attributes['screen_size'] = str(dim)+'x'+str(int(dim*9/16))
                    new_attributes['air_conditioned'] = random.choice([1,1,1,1,1,0])
                    new_attributes['multiple_stages'] = random.choice([1,1,0,0,0,0])
                if self.level == 2:
                    tot = len(self.all_child)
                    n = int(tot / 16) + 1
                    m = int(tot / 9) + 1
                    places = {0: 'A', 1: 'B', 2: 'C', 3: 'D', 4: 'E', 5: 'F', 6: 'G', 7: 'H',
                              8: 'I', 9: 'J', 10: 'K', 11: 'L', 12: 'M', 13: 'N', 14: 'O',
                              15: 'P', 16: 'Q', 17: 'R', 18: 'S', 19: 'T'}
                    new_attributes['position_number'] = i
                    new_attributes['auditorium_number'] = attributes['auditorium_number']
                    new_attributes['seat_place'] = places[int(i/n)] + str(i%n+1)
                    new_attributes['cinema_id'] = attributes['cinema_id']

                if self.level == 0:
                    new_position.append(cities[i])
                else:
                    new_position.append(str(i))

                self.all_child[i] = Tree(                                           # Creazione ricorsiva dei rami figlio
                                         level = self.level +1,
                                         random_gen = True,
                                         position = new_position,
                                         attributes = new_attributes
                                         )
        return


    def __str__(self):
        return str(self.position)

    def print_tree(self, level=0):                                                          # Print della struttura tree
        if self.level == level:
            print(self.position, self.attributes)
            #print('level {}: '.format(level), self.attributes)
        for child in self.all_child:
            if child != None: child.print_tree(level)


    def create_dict(self, level=0):                                                         # Creazione delle tabelle:
        thisdb = db0                                                                        # Cinemas
        if level == 1:                                                                      # Auditoria
            thisdb = db1                                                                    # Seats
        if level == 2:                                                                      # al variare di level (1,2,3)
            thisdb = db2
        if level == 3:
            thisdb = db3
        if self.level == level:
            if len(thisdb.keys())==0:
                for key in self.attributes.keys():
                    thisdb[key] = []
            for key in self.attributes.keys():
                thisdb[key].append(self.attributes[key])
        for child in self.all_child:
            if child != None: child.create_dict(level)


db0 = {}
db1 = {}
db2 = {}
db3 = {}
def createRoot(level = 0):
    random.seed(1)
    dict = GU.createUsers()
    if level == 0:
        thisdb = db0
        UniCinema = Tree(0, random_gen=True, dict=dict)
        stolen_identities.sort(reverse=True)
        for i in range(len(dict['city']) - 1, -1, -1):
            if stolen_identities.__contains__(i):
               for key in dict:
                   del dict[key][i]
        return dict

    thisdb = dict
    if level == 1:                                                                      # Creazione effettiva dei dizionari
        thisdb = db1                                                                    # che verranno iniettati come tabelle
    if level == 2:                                                                      # in Oracle DB
        thisdb = db2
    if level == 3:
        thisdb = db3

    UniCinema = Tree(0, random_gen=True, dict=dict)
    UniCinema.create_dict(level)
    UniCinema.print_tree(2)
    return thisdb