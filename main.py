from flask import Flask, request
from threading import Thread
from queue import Queue
import requests
import time
import json
import logging
import os

app = Flask(__name__)
queue = Queue()
logging.basicConfig(level=logging.INFO)

requests_dict = {}

def send_request(user_operation_hash, chain):
    try:
        url = f"http://{os.environ['BUNDLER_IP']}/bundler/{chain}"
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
        url = f"http://{os.environ['GUARDIAN_IP']}/guardian/update/"
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


MAX_WAIT_TIME = 60

def worker():
    while True:
        user_operation_hash, chain, start_time = queue.get()
        elapsed_time = time.time() - start_time
        if elapsed_time > MAX_WAIT_TIME:
            logging.warning(f"Transaction {user_operation_hash} expired from queue after {MAX_WAIT_TIME}s")
            continue
        if time.time() - requests_dict.get((user_operation_hash, chain), 0) < 5:
            queue.put((user_operation_hash, chain, start_time))
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
            queue.put((user_operation_hash, chain, start_time))
            requests_dict[(user_operation_hash, chain)] = time.time()


@app.route('/trigger/', methods=['POST'])
def trigger():
    data = request.get_json()
    user_operation_hash = data.get('user_operation_hash')
    chain = data.get('chain')
    if not user_operation_hash or not chain:
        return {"success": False, "error": "Missing required parameters"}, 400
    start_time = time.time()
    queue.put((user_operation_hash, chain, start_time))
    requests_dict[(user_operation_hash, chain)] = start_time
    return {'success': True, 'status': 'added to queue'}, 202

if __name__ == "__main__":
    worker = Thread(target=worker)
    worker.start()
    app.run(host='0.0.0.0', port=12004)
