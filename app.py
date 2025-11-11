from flask import Flask, request, jsonify
from flask_cors import CORS
from fer.fer import FER
import cv2
import numpy as np
import base64
from web3 import Web3
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# --- Blockchain Setup ---
RPC_URL = os.getenv("RPC_URL")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

# Initialize web3 connection
web3 = Web3(Web3.HTTPProvider(RPC_URL))

# --- Contract ABIs ---
ABI_TOKEN = [
    {
        "inputs": [
            {"internalType": "address", "name": "recipient", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [
            {"internalType": "bool", "name": "", "type": "bool"}
        ],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

ABI_ESCROW = [
    {
        "inputs": [
            {"internalType": "address", "name": "user", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "rewardUser",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

# --- Contract Setup ---
TOKEN_CONTRACT_ADDRESS = web3.to_checksum_address(os.getenv("TOKEN_CONTRACT_ADDRESS"))
ESCROW_CONTRACT_ADDRESS = web3.to_checksum_address(os.getenv("ESCROW_CONTRACT_ADDRESS"))

token_contract = web3.eth.contract(address=TOKEN_CONTRACT_ADDRESS, abi=ABI_TOKEN)
escrow_contract = web3.eth.contract(address=ESCROW_CONTRACT_ADDRESS, abi=ABI_ESCROW)

# Load the account (this will be the reward sender)
account = web3.eth.account.from_key(PRIVATE_KEY)

# --- Emotion Detector Setup ---
detector = FER(mtcnn=True)


# --- Emotion Detection Route ---
@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json
    image_base64 = data.get("image")
    user_address = data.get("address")
    
    if not image_base64:
        return jsonify({"error": "No image provided"}), 400

    # Decode base64 image
    img_bytes = base64.b64decode(image_base64.split(",")[1])
    np_arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    # Detect emotion
    emotion, score_val = detector.top_emotion(img)
    score = int((score_val or 0) * 100)
    
    # Auto-reward if score >= 50 and address provided
    rewarded = False
    tx_hash = None
    
    if user_address and score >= 50:
        try:
            user_address = web3.to_checksum_address(user_address)
            
            tx = escrow_contract.functions.rewardUser(user_address, 5 * (10 ** 18)).build_transaction({
                'from': account.address,
                'gas': 300000,
                'gasPrice': web3.to_wei('10', 'gwei'),
                'nonce': web3.eth.get_transaction_count(account.address),
            })
            
            signed_tx = web3.eth.account.sign_transaction(tx, PRIVATE_KEY)
            tx_hash_bytes = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash = tx_hash_bytes.hex()
            rewarded = True
            
            print(f"✅ Reward sent to {user_address}")
            print(f"🔗 Tx: https://sepolia.etherscan.io/tx/{tx_hash}")
        except Exception as e:
            print(f"❌ Reward failed: {str(e)}")
    
    return jsonify({
        "emotion": emotion or "neutral",
        "score": score,
        "rewarded": rewarded,
        "txHash": tx_hash
    })


# --- Reward Claim Route ---
@app.route("/claim-reward", methods=["POST"])
def claim_reward():
    data = request.get_json()
    address = data.get("address")
    score = data.get("score")

    if not address:
        return jsonify({"status": "error", "message": "Missing wallet address"}), 400
    if score < 250:
        return jsonify({"status": "error", "message": "Score too low for reward"}), 400

    try:
        # ✅ Convert to checksum address (fixes your current error)
        user_address = web3.to_checksum_address(address)

        # ✅ Build transaction
        tx = escrow_contract.functions.rewardUser(user_address, 5 * (10 ** 18)).build_transaction({
            'from': account.address,
            'gas': 300000,
            'gasPrice': web3.to_wei('10', 'gwei'),
            'nonce': web3.eth.get_transaction_count(account.address),
        })

        # ✅ Sign and send
        signed_tx = web3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)

        # Log transaction info in backend console
        print(f"✅ Reward sent to {user_address}")
        print(f"🔗 Tx Link: https://sepolia.etherscan.io/tx/{tx_hash.hex()}")

        return jsonify({
            "status": "success",
            "txHash": tx_hash.hex(),
            "message": "Reward successfully claimed!"
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
