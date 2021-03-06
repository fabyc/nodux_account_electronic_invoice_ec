#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
#! -*- coding: utf8 -*-
from trytond.pool import *
import logging
from importlib import import_module
from trytond.model import ModelView, ModelSQL, fields
from trytond.wizard import Wizard, StateTransition, StateView, Button
from trytond.pyson import Bool, Eval, Id
from trytond.transaction import Transaction
import re

__all__ = ['Party']

STATES = {
    'readonly': ~Eval('active', True),
    'required': True,
}
DEPENDS = ['active']

class Party:
    __metaclass__ = PoolMeta
    __name__ = 'party.party'

    contact_mechanisms2 = fields.One2Many('party.contact_mechanism', 'party',
        'Contact Mechanisms', states=STATES, depends=DEPENDS, help = u'Requerido ingresar un correo electronico')

    @classmethod
    def __setup__(cls):
        super(Party, cls).__setup__()
        cls._error_messages.update({
                'invalid_contact': (u'Es requerido ingresar un correo, para el envio de comprobantes electronicos'),
                'invalid_structure':('Correo electronico no cumple con la estructura (ejemplo@mail.com)')})

    @classmethod
    def validate(cls, parties):
        super(Party, cls).validate(parties)
        for party in parties:
            party.validate_email()

    def validate_email(self):
        correo = ''
        correos = self.contact_mechanisms
        for c in correos:
            print c
            if c.type == 'email':
                correo = c.value
                if re.match("[_a-z0-9-]+(\.[_a-z0-9-]+)*@[a-z0-9-]+(\.[a-z0-9-]+)*(\.[a-z]{2,3})", correo):
                    pass
                else:
                    self.raise_user_error('invalid_structure')
        if correo != '':
            pass
        else:
            self.raise_user_error('invalid_contact')
