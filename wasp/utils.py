from collections import defaultdict


class QueryParams(defaultdict):
    """
    A dictionary that stores multiple values per key.

    this has all the normal dictionary methods, and works as normal but does
    not override a key when `add` is used, and also has `getall`
    """
    __slots__ = ['mappings']

    def __init__(self):
        super().__init__(list)
        self.super = super()

    def get(self, name, default=None):
        return self.super.get(name, [default])[0]

    def getall(self, name, default=None):
        return self.super.get(name, default)

    def __getitem__(self, key):
        try:
            return self.super.__getitem__(key)[0]
        except IndexError:
            raise KeyError('Invalid Key: {key}'.format(key))

    def __setitem__(self, key, value):
        raise TypeError('MultiDict does not support item assignment. '
                        'Use .add(k, v) instead.')

    def add(self, name, value):
        self.super[name].append(value)




