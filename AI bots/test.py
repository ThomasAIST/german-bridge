import random
import copy
import timeit


batch_size = 32

def test():
    row = list(range(52))
    return [row[:] for _ in range(batch_size)]

def test2():
    row = list(range(52))
    return [copy.deepcopy(row) for _ in range(batch_size)]

print(f'{timeit.timeit("test()", setup="from test import test", number=10000)} seconds 1')
print(f'{timeit.timeit("test2()", setup="from test import test2", number=10000)} seconds')