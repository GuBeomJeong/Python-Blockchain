import hashlib
import json

from textwrap import dedent
from time import time
from uuid import uuid4

from flask import Flask, jsonify, request
from urllib.parse import urlparse

import requests


class Blockchain(object):
    def __init__(self):
        self.chain = []
        self.current_transactions = []
        self.new_block(previous_hash=1, proof=100)
        self.nodes = set()

    def new_block(self, proof, previous_hash=None):
        """
        블록체인에 새로운 블록 만들기

        :param proof:
        :param previous_hash: <str> 이전 블록의 해쉬값
        :return: <dict> 새로운 블록

        """

        block = {
            'index': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': proof,
            'previous_hash': previous_hash or self.hash(self.chain[-1])
        }

        # 거래 내역 초기화
        self.current_transactions = []

        self.chain.append(block)
        return block

    # Adds a new transaction to the list of transactions
    def new_transaction(self, sender, recipient, amount):
        """
        다음 채굴될 블록(새로운 블록)에 들어갈 거래내역

        :param sender:
        :param recipient:
        :param amount:
        :return: <int> 이 거래를 포함할 블록의 index 값
        """

        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
        })

        return self.last_block['index'] + 1

    @staticmethod
    def hash(block):
        """
        SHA-256

        :param block: <dick>
        :return:
        """

        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    @property
    def last_block(self):
        return self.chain[-1]

    def proof_of_work(self, last_proof):
        """
        앞에서 0의 개수가 4개가 나오는 hash(pp')를 만족시키는 p'를 찾는다.
        p는 이전 블록의 proof, p'는 새로운 블록의 proof

        :param last_proof: <int>
        :return: <int>
        """

        proof = 0
        while self.valid_proof(last_proof, proof) is False:
            proof += 1

        return proof

    @staticmethod
    def valid_proof(last_proof, proof):
        """
        Proof 검증 : hash 값의 앞 4(난이도에 따라 다름)자리가 0인지
        :param last_proof: <int> 이전 블록의 proof 값
        :param proof: <int> 현재 블록의 proof 값
        :return: <bool>
        """

        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"

    # 블록체인에 있어서 가장 중요한 것은 '탈중앙화' 되어야 한다는 것이다.
    # 탈중앙화 되었을 때 모든 노드들이 같은 체인을 가지고 있는지와 유효한 블록체인인지 확인하기 위해
    # '합의 알고리즘'이 필요하다.
    # 합의 알고리즘을 적용하기 위해서는 네트워크에 있는 이웃 노드들을 알아야 한다.
    # 우리 네트워크의 각 노드들은 네트워크 내 다른 노드들의 정보를 가지고 있어야 한다.
    def register_node(self, address):
        """
        새로운 노드가 기존의 노드의 list에 등록
        'http://172.0.0.1:5002 와 같은 형태로 등록을 요청

        :param address:
        :return:
        """

        parsed_url = urlparse(address)
        self.nodes.add(parsed_url.netloc)

    def valid_chain(self, chain):
        # 주어진 블록체인이 유효한지 결정
        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            block = chain[current_index]
            print(f'{last_block}')
            print(f'{block}')
            print("\n---------\n")

            if block['previous_hash'] != self.hash(last_block):
                return False

            if not self.valid_proof(last_block['proof'], block['proof']):
                return False

            if not self.valid_proof(last_block['proof'], block['proof']):
                return False

            last_block = block
            current_index += 1

        return True

    # 모든 이웃 노드들에게, 그들의 체인을 다운 받고 규칙(가장 긴 체인이 유효한 체인)을 통해
    # 유효한 체인(가장 긴 체인을 보유하고 있는지)인지 확인하는 함수
    # 만약 valid chain이 우리의 것보다 더 길다면, 우리 것은 대체된다.
    def resolve_conflicts(self):
        """
        합의 알고리즘
        노드 중에서 가장 긴 체인을 가지고 있는 노드의 체인을 유효한 것으로 인정하기로 함
        :return:

        """

        neighbours = self.nodes
        new_chain = None

        max_length = len(self.chain)

        for node in neighbours:
            response = requests.get(f'http://{node}/chain')

            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain

            if new_chain:
                self.chain = new_chain
                return True

        return False


app = Flask(__name__)

# Generate a globally unique address for this node
node_identifier = str(uuid4()).replace('-', '')

blockchain = Blockchain()


@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain)
    }
    return jsonify(response), 200


@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json()

    # 요청된 필드가 POST 된 데이터인지 확인
    required = ['sender', 'recipient', 'amount']
    if not all(k in values for k in required):
        return 'Missing values', 400

    # 새로운 거래 생성
    index = blockchain.new_transaction(values['sender'], values['recipient'], values['amount'])

    response = {'message': f'Transaction will be added to Block {index}'}
    return jsonify(response), 201


@app.route('/mine', methods=['GET'])
def mine():
    """
    1. POW 계산
    2. 채굴자에게 거래를 추가한 것에 대한 보상으로 1 코인을 준다.
    3. 새 블록을 체인에 추가한다.
    :return:
    """
    # 다음 블록의 proof 값을 얻어내기 위해 POW 알고리즘을 수행한다.
    last_block = blockchain.last_block
    last_proof = last_block['proof']
    proof = blockchain.proof_of_work(last_proof)

    # proof 값을 찾으면(채굴에 성공하면) 보상을 준다.
    # sender의 주소를 0으로 한다.
    # (원래 거래는 송신자, 수신자가 있어야 하는데 채굴에 대한 보상으로 얻은 코인은 송신자를 0으로 한다
    blockchain.new_transaction(
        sender="0",
        recipient=node_identifier,
        amount=1
    )

    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(proof, previous_hash)

    response = {
        'message': "New Block Forged",
        'index': block['index'],
        'transactions': block['transactions'],
        'proof': block['proof'],
        'previous_hash': block['previous_hash']
    }

    return jsonify(response), 200


# URL 형태로 새로운 노드들을 등록
@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_json()

    nodes = values.get('nodes')

    if nodes is None:
        return "Error: supply a valid list of nodes", 400

    for node in nodes:
        blockchain.register_node(node)

    response = {
        'message': 'New nodes have been added',
        'total_nodes': list(blockchain.nodes),
    }
    return jsonify(response), 201


# 가장 긴 체인을 가지고 있는 노드가 정확한 체인을 가지고 있다는 가정아래
# 모든 분쟁을 해결할 수 있는 합의 알고리즘을 적용
@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = blockchain.resolve_conflicts()

    if replaced:
        response = {
            'message': 'Our chain was replaced',
            'new_chain': blockchain.chain
        }
    else:
        response = {
            'message': 'Our chain is authoritative',
            'chain': blockchain.chain
        }

    return jsonify(response), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
