import hashlib
import json
import rsa
import time


# -------------------- STRUKTURY --------------------
class Transaction:
    def __init__(self, sender, recipient, amount, signature):
        self.sender = sender
        self.recipient = recipient
        self.amount = amount
        self.signature = signature

    def to_dict(self):
        return {
            'sender': self.sender,
            'recipient': self.recipient,
            'amount': self.amount,
            'signature': self.signature
        }

    @staticmethod
    def from_dict(data):
        return Transaction(data['sender'], data['recipient'], data['amount'], data['signature'])


class Block:
    def __init__(self, index, transactions, timestamp, previous_hash, nonce=0):
        self.index = index
        self.transactions = transactions
        self.timestamp = timestamp
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.hash = self.compute_hash()

    def compute_hash(self):
        block_string = json.dumps({
            'index': self.index,
            'transactions': self.transactions,
            'timestamp': self.timestamp,
            'previous_hash': self.previous_hash,
            'nonce': self.nonce
        }, sort_keys=True, default=str)
        return hashlib.sha256(block_string.encode()).hexdigest()

    def to_dict(self):
        return self.__dict__

    @staticmethod
    def from_dict(data):
        b = Block(data['index'], data['transactions'], data['timestamp'], data['previous_hash'], data['nonce'])
        b.hash = data['hash']
        return b


# -------------------- BLOCKCHAIN --------------------
class Blockchain:
    difficulty = 2

    def __init__(self):
        self.chain = []
        self.pending_transactions = []
        self.create_genesis_block()
        self.balances = {}
        self.public_keys = {}

    def create_genesis_block(self):
        genesis_block = Block(0, [], time.time(), "0")
        self.chain.append(genesis_block)

    def add_transaction(self, transaction):
        if self.verify_transaction(transaction):
            self.pending_transactions.append(transaction)

    def verify_transaction(self, transaction):
        if transaction.sender == "0":  # System (nagroda)
            return True
        try:
            pubkey_pem = self.public_keys.get(transaction.sender)
            if not pubkey_pem:
                return False
            pubkey = rsa.PublicKey.load_pkcs1(pubkey_pem.encode())
            rsa.verify(f"{transaction.sender}{transaction.recipient}{transaction.amount}".encode(), bytes.fromhex(transaction.signature), pubkey)
            return self.balances.get(transaction.sender, 0) >= transaction.amount
        except Exception as e:
            return False

    def mine_block(self, miner_address):
        self.pending_transactions.append(Transaction("0", miner_address, 1.0, ""))
        new_block = Block(
            index=len(self.chain),
            transactions=[tx.to_dict() for tx in self.pending_transactions],
            timestamp=time.time(),
            previous_hash=self.chain[-1].hash
        )
        while not new_block.hash.startswith("0" * self.difficulty):
            new_block.nonce += 1
            new_block.hash = new_block.compute_hash()

        self.chain.append(new_block)
        self.update_balances(self.pending_transactions)
        self.pending_transactions = []

    def update_balances(self, transactions):
        for tx in transactions:
            if tx.sender != "0":
                self.balances[tx.sender] -= tx.amount
            self.balances[tx.recipient] = self.balances.get(tx.recipient, 0) + tx.amount

    def replace_chain(self, new_chain):
        if len(new_chain) > len(self.chain):
            self.chain = new_chain