#!/usr/bin/env python3

import simpy
import pandas as pd
import math
import random
import matplotlib.pyplot as plt
import plotly.graph_objs as go

# Global parameters for brew house characteristics and sales information.
KEG_CAPACITY = 3000 
INITIAL_BEER_INVENTORY = 2000
GRAIN_PER_BATCH = 3
PINTS_PER_BATCH = 440
DAILY_SALES_LOW = 24
DAILY_SALES_HIGH = 104
GRAIN_PER_ORDER = 200
INVENTORY_LOW = 95

# Define the beer class as the agent moving through the simulation.
class Beer:
    def __init__(self, beer_name, beer_type, beer_price, yeast_type, brew_time, ferm_time, condition_time, batch_size):
        '''Beer class used to track beer characteristics, price points, and brew ops timelines.'''
        self.beer_name = beer_name
        self.beer_type = beer_type
        self.beer_price = beer_price
        self.yeast_type = yeast_type
        self.brew_time = brew_time
        self.ferm_time = ferm_time
        self.condition_time = condition_time
        self.batch_size = batch_size
        self.brew_log = {}
        self.brew_history = []

class GrainStore(simpy.Container):
    '''GrainStore is a monitored container that allows the inventory manager to track and order supplies when necessary.'''
    def __init__(self, env, capacity=float('inf'), init=0):
        super().__init__(env, capacity, init)
        self.env = env
        self.data = []

    def put(self, *args, **kwargs):
        self.data.append((self.env.now, self.level))
        return super().put(*args, **kwargs)

    def get(self, *args, **kwargs):
        self.data.append((self.env.now, self.level))
        print(f'The grain level is {self.level}.')
        return super().get(*args, **kwargs)

class FermentationTank(simpy.Container):
    def __init__(self, env, capacity=float('inf'), init=0, tank_id=None):
        super().__init__(env, capacity, init)
        self.tank_id = tank_id
        self.env = env
        self.data = []

    def add_beer(self, beer):
        yield self.put(1)  # Adding 1 unit to the tank, representing the beer
        self.data.append((self.env.now, self.env.now+beer.ferm_time, beer.beer_name,self.tank_id))
        yield self.env.timeout(beer.ferm_time)
        #self.data.append((env.now, f'Finishing fermenting {beer.beer_name} in tank {self.tank_id}'))
        yield self.get(1)  # Removing the beer after fermentation is complete

class ProductionStore(simpy.Container):
    def __init__(self, env, capacity=float('inf'), init=0):
        super().__init__(env, capacity, init)
        self.env = env
        self.data = []

    def put(self, *args, **kwargs):
        self.data.append((self.env.now, self.level))
        return super().put(*args, **kwargs)

    def get(self, *args, **kwargs):
        self.data.append((self.env.now, self.level))
        print(f'The grain level is {self.level}.')
        return super().get(*args, **kwargs)

class Brewhouse:
    '''Brewhouse class captures the brew house actions, number of resources, and inventory parameters for the simulation.'''
    def __init__(self, env, num_kettles, tanks, num_britetanks, num_customers, num_orders, prod_inv, pils_inv):
        self.env = env
        self.kettles = simpy.Resource(env, num_kettles)
        self.fermtanks = tanks
        self.britetanks = simpy.Resource(env, num_britetanks)
        self.pils_grain = pils_inv
        self.production = prod_inv  # GLOBAL Parameters
        self.tap_list = {}
        self.customers = num_customers
        self.orders = num_orders
        self.profit = 0
        self.profit_timeline = []
        self.beers_sold = 0

    def brew(self, beer):
        '''Brew day process. Ranges from 0.5 to 1.5 days.'''
        beer.brew_log['brew_date'] = self.env.now
        yield self.pils_grain.get(GRAIN_PER_BATCH)  # GLOBAL Parameters
        yield self.env.timeout(beer.brew_time)

    def ferment(self, beer):
        '''Process to ferment the beers in the fermentation vessels for the appropriate time.'''
        beer.brew_log['ferm_date'] = self.env.now
        yield self.env.timeout(beer.ferm_time)

    def condition(self, beer):
        '''Process to condition and carbonate beer for packaging.'''
        beer.brew_log['brite_date'] = self.env.now
        yield self.env.timeout(beer.condition_time)

    def package(self, beer):
        beer.brew_log['package_date'] = self.env.now
        beer.brew_history.append(beer.brew_log)
        yield self.production.put(PINTS_PER_BATCH)  # GLOBAL parameters, number of pints per batch
        print(self.production.level)

    def sell_beer(self):
        order = random.randint(DAILY_SALES_LOW, DAILY_SALES_HIGH)  # GLOBAL PARAMETERS, low and high daily sales
        if self.production.level >= order:
            self.profit += order * 6.50  # Stand-in price
            profit_triple = (self.env.now, self.beers_sold, self.profit)
            self.profit_timeline.append(profit_triple)
            self.beers_sold += order
            yield self.production.get(order)
        else:
            print('Unable to fulfill taproom order.')

    def buy_inventory(self):
        print('Inventory Manager purchased grain.')
        yield self.pils_grain.put(GRAIN_PER_ORDER)  # GLOBAL parameters, inventory manager buys

def brew_ops(env, beer_list, bh):
    '''Routing operations for brew house.'''
    tank_index = 0  # Used to cycle through

    while True:
        beer = random.choice(beer_list)
        print(f'At {env.now} Brewhouse is requesting to brew {beer.beer_name}')
        with bh.kettles.request() as request:
            yield request
            print(f'Brewhouse has started brewing {beer.beer_name}')
            yield env.process(bh.brew(beer))
            print(f'Brewhouse has finished brewing {beer.beer_name} after {beer.brew_time}')

        print(f'At {env.now} Brewhouse is requesting to ferment {beer.beer_name}')
        for _ in range(len(bh.fermtanks)):
            fermtank = bh.fermtanks[tank_index]
            tank_index = (tank_index + 1) % len(bh.fermtanks)
            if fermtank.level <= fermtank.capacity:
                yield env.process(fermtank.add_beer(beer))
                print(f'Brewhouse has moved {beer.beer_name} to fermentation tank {fermtank.tank_id}.')
                break
        else:
            print(f'No fermentation tanks available for {beer.beer_name} at {env.now}.')

        print(f'At {env.now} Brewhouse is requesting to condition {beer.beer_name}')
        with bh.britetanks.request() as request:
            yield request
            print(f'Brewhouse has moved {beer.beer_name} to the brite tank.')
            yield env.process(bh.condition(beer))
            print(f'Brewhouse is conditioning {beer.beer_name} for {beer.condition_time}')

        print(f'At {env.now} Brewhouse has packaged {beer.beer_name}')
        yield env.process(bh.package(beer))

        yield env.timeout(0)

def tap_room_ops(env, bh):
    '''Sell beer in the taproom.'''
    while True:
        yield env.process(bh.sell_beer())
        print(f'{env.now}: Front house has sold beer. Current tap inv is: {bh.production.level}')
        yield env.timeout(1)

def inventory_man(env, inventory, bh):
    '''Manage grain inventory.'''
    while True:
        if inventory.level < INVENTORY_LOW:  # GLOBAL parameter, low inventory
            yield env.process(bh.buy_inventory())
            print(f'The {inventory} level is restocked to: {inventory.level}.')
        else:
            yield env.timeout(5)
            if env.now >= 100:
                print(f'The inventory is done being managed.')
                break

def monitor_tanks(env, beer_list, bh):
    '''Monitors fermentation tanks and starts a new brewing process when a tank is empty.'''
    while True:
        available_tanks = [tank for tank in bh.fermtanks if tank.level < tank.capacity]
        if available_tanks:
            print(f'At {env.now}, an empty fermentation tank is available. Starting a new brew...')
            env.process(brew_ops(env, beer_list, bh))
        else:
            print(f'At {env.now}, no empty fermentation tanks. Waiting to start a new brew...')
        yield env.timeout(10)

def main():
    env = simpy.Environment()
    tank_1 = FermentationTank(env, capacity=1, tank_id=1)
    tank_2 = FermentationTank(env, capacity=1, tank_id=2)
    tanks = [tank_1, tank_2]

    bh = Brewhouse(env, 3, tanks, 2, 20, 5,
                   ProductionStore(env, capacity=KEG_CAPACITY, init=INITIAL_BEER_INVENTORY),
                   GrainStore(env, capacity=400, init=250))
    
    # Example beers for example simulation.
    tripel = Beer('Tripel', 'Tripel', 8.00, 'WLP530 Abbey Ale', 1, 10, 5, 20)
    dIPA = Beer('DIPA', 'DIPA', 7.50, 'London III', 0.5, 7, 5, 30)
    pils = Beer('Pils', 'Pils', 5.00, 'WLP800 German Lager', 1.5, 14, 7, 60)
    beer_list = [tripel, dIPA, pils]

    env.process(inventory_man(env, bh.pils_grain, bh))
    env.process(tap_room_ops(env, bh))
    env.process(monitor_tanks(env, beer_list, bh))

    env.run(until=365)

if __name__ == "__main__":
    main()
