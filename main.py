from flask import Flask, request
from threading import Thread
from queue import Queue
import requests
import time
import json
import logging

app = Flask(__name__)
queue = Queue()
logging.basicConfig(level=logging.INFO)

requests_dict = {}

def send_request(user_operation_hash, chain):
    try:
        url = f"http://3.38.245.156/bundler/{chain}"
        headers = {"Content-Type": "application/json"}
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_getUserOperationByHash",
            "params": [user_operation_hash]
        }
        response = requests.post(url, headers=headers, data=json.dumps(data))
        response.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"Error sending request: {e}")
        return None
    return response.json()

def update_transaction(transaction_hash, chain):
    try:
        url = "http://3.38.245.156/guardian/update/txn/"
        headers = {"Content-Type": "application/json"}
        data = {
            "transaction_hash": transaction_hash,
            "chain": chain
        }
        response = requests.post(url, headers=headers, data=json.dumps(data))
        response.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"Error updating transaction: {e}")
        return None
    return response.json()

def worker():
    while True:
        user_operation_hash, chain = queue.get()
        logging.info(f"Checking {user_operation_hash}")
        if time.time() - requests_dict.get((user_operation_hash, chain), 0) < 5:
            queue.put((user_operation_hash, chain))
            time.sleep(1)
            continue
        logging.info(f"Sending request for {user_operation_hash}")
        response = send_request(user_operation_hash, chain)
        if response and 'result' in response:
            transaction_hash = response['result']['transactionHash']
            update_response = update_transaction(transaction_hash, chain)
            logging.info(f"Transaction update response: {update_response}")
        elif response and 'error' in response:
            logging.error(f"Error: {response['error']['message']}")
            queue.put((user_operation_hash, chain))
            requests_dict[(user_operation_hash, chain)] = time.time()

@app.route('/trigger/', methods=['POST'])
def trigger():
    data = request.get_json()
    user_operation_hash = data.get('user_operation_hash')
    chain = data.get('chain')
    if not user_operation_hash or not chain:
        return {"success": False, "error": "Missing required parameters"}, 400
    queue.put((user_operation_hash, chain))
    requests_dict[(user_operation_hash, chain)] = time.time()
    return {'success': True, 'status': 'added to queue'}, 202

if __name__ == "__main__":
    worker = Thread(target=worker)
    worker.start()
    app.run(host='0.0.0.0', port=12004)
