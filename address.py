#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from trytond.model import ModelView, ModelSQL, fields
from trytond.pyson import Eval, If
from trytond.pool import Pool, PoolMeta

__all__ = ['Address']
__metaclass__ = PoolMeta

class Address(ModelSQL, ModelView):
    "Address"
    __name__ = 'party.address'

    @classmethod
    def __setup__(cls):
        super(Address, cls).__setup__()
        cls.street.states['required'] = Eval('active', True)
