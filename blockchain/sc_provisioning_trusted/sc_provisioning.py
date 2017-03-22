"""
Copyright 2016 Disney Connected and Advanced Technologies

Licensed under the Apache License, Version 2.0 (the "Apache License")
with the following modification; you may not use this file except in
compliance with the Apache License and the following modification to it:
Section 6. Trademarks. is deleted and replaced with:

     6. Trademarks. This License does not grant permission to use the trade
        names, trademarks, service marks, or product names of the Licensor
        and its affiliates, except as required to comply with Section 4(c) of
        the License and to reproduce the content of the NOTICE file.

You may obtain a copy of the Apache License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the Apache License with the above modification is
distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
KIND, either express or implied. See the Apache License for the specific
language governing permissions and limitations under the Apache License.
"""

__author__ = "Joe Roets, Brandon Kite, Dylan Yelton, Michael Bachtel"
__copyright__ = "Copyright 2016, Disney Connected and Advanced Technologies"
__license__ = "Apache"
__version__ = "2.0"
__maintainer__ = "Joe Roets"
__email__ = "joe@dragonchain.org"

import logging

from blockchain.db.postgres import smart_contracts_db as sc_dao
from blockchain.db.postgres import sub_to_db as sub_db

import time
import uuid


def logger(name="verifier-service"):
    return logging.getLogger(name)


class SmartContractProvisioning(object):
    def __init__(self, network=None, public_key=None):
        # processing nodes network
        self.network = network
        # processing node's public key
        self.public_key = public_key
        self.rtsc = {"TT_SUB_REQ": self.subscription_request,
                     "TT_PROVISION_SC": self.provision_sc}
        # user/business transaction smart contracts
        self.tsc = {}
        # subscription smart contracts
        self.ssc = {}
        # arbitrary/library smart contracts
        self.lsc = {}
        # broadcast receipt smart contracts
        self.bsc = {}

        # dictionary to hold smart contract structures sc_class => sc dict
        self.sc_container = {"tsc": self.tsc, "ssc": self.ssc, "lsc": self.lsc, "bsc": self.bsc}

        # load existing smart contracts from database
        self.load_scs()
        pass

    def subscription_request(self, transaction):
        """
            attempts to make initial communication with subscription node
            param transaction: transaction to retrieve subscription info from
        """
        # check if given transaction has one or more subscriptions tied to it and inserts into subscriptions database
        if self.network and self.public_key:
            if "subscription" in transaction["payload"]:
                subscription = transaction["payload"]['subscription']
                try:
                    subscription_id = str(uuid.uuid4())
                    criteria = subscription['criteria']
                    phase_criteria = subscription['phase_criteria']
                    subscription['create_ts'] = int(time.time())
                    # store new subscription info
                    sub_db.insert_subscription(subscription, subscription_id)
                    # get subscription node
                    subscription_node = self.network.get_subscription_node(subscription)
                    # initiate communication with subscription node
                    if subscription_node:
                        subscription_node.client.subscription_provisioning(subscription_id, criteria, phase_criteria, subscription['create_ts'], self.public_key)
                    return True
                except Exception as ex:  # likely already subscribed
                    template = "An exception of type {0} occurred. Arguments:\n{1!r}"
                    message = template.format(type(ex).__name__, ex.args)
                    logger().warning(message)
                    return False
        else:
            logger().warning("Could not fulfill subscription request: no network or public key provided.")
            return False

    def provision_sc(self, transaction):
        return True

    def provision_tsc(self, transaction):
        """
        provision tsc type smart contract
        :param transaction: transaction to extract sc data from
        """
        pl = transaction['payload']
        sc_key = transaction['payload']['transaction_type']
        # insert new sc into database
        if not self._insert_sc(pl, "tsc", sc_key):
            return False
        return self._sc_provisioning_helper(pl, "tsc", sc_key)

    def provision_ssc(self, transaction):
        pl = transaction['payload']
        criteria = pl['criteria']
        sc_key = ""
        if "origin_id" in criteria:
            if "origin_id" in pl and pl['origin_id']:
                sc_key = pl['origin_id']
            else:
                return False
        sc_key += ":"
        if "transaction_type" in criteria:
            if "transaction_type" in pl and pl['transaction_type']:
                sc_key += pl['transaction_type']
            else:
                return False
        sc_key += ":"
        if "phase" in criteria:
            if "phase" in pl and pl['phase']:
                sc_key += pl['phase']
            else:
                return False
        # insert new sc into database
        if not self._insert_sc(pl, "ssc", sc_key):
            return False
        return self._sc_provisioning_helper(pl, "ssc", sc_key)

    def provision_lsc(self, transaction):
        return True

    def provision_bsc(self, transaction):
        sc_key = ""
        return self._sc_provisioning_helper(transaction['payload'], "bsc", sc_key)

    def _sc_provisioning_helper(self, pl, sc_class, sc_key):
        """
        insert sc code into appropriate dictionary
        :param pl: transaction payload to extract sc from
        :param sc_class: type of sc being dealt with (e.g. tsc, ssc, etc.)
        """
        try:
            if 'smart_contract' in pl:
                sc = pl['smart_contract']
                if sc[sc_class]:
                    func = None
                    # define sc function
                    exec(sc[sc_class])
                    # store sc function for this txn type
                    self.sc_container[sc_class][sc_key] = func
                else:
                    logger().warning("No smart contract code provided...")
                    return False
            else:
                return False
        except Exception as ex:
            template = "An exception of type {0} occurred. Arguments:\n{1!r}"
            message = template.format(type(ex).__name__, ex.args)
            logger().warning(message)
            return False
        return True

    def _insert_sc(self, pl, sc_class, sc_key):
        """ insert sc info into database """
        try:
            sc_dao.insert_sc(pl, sc_class, sc_key)
        except Exception as ex:
            template = "An exception of type {0} occurred. Arguments:\n{1!r}"
            message = template.format(type(ex).__name__, ex.args)
            logger().warning(message)
            return False
        return True

    # FIXME: only load highest version sc to avoid overwriting
    def load_scs(self):
        """ load existing smart contracts from database """
        try:
            scs = sc_dao.get_all()
            for sc in scs:
                sc_class = sc['sc_class']
                sc_key = sc['sc_key']
                if sc_class in self.sc_container:
                    func = None
                    # define sc function
                    exec(sc['smart_contract'])
                    self.sc_container[sc_class][sc_key] = func
        except Exception as ex:
            template = "An exception of type {0} occurred. Arguments:\n{1!r}"
            message = template.format(type(ex).__name__, ex.args)
            logger().warning(message)


if __name__ == '__main__':
    scp = SmartContractProvisioning()
    scp.load_scs()
