import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'     # Suppress TensorFlow logging

from flask import Flask, request, jsonify
from flask_cors import CORS
from fer import FER
import cv2
import numpy as np
import base64
from web3 import Web3
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# ---------- Blockchain Setup ----------
RPC_URL = os.getenv("RPC_URL")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
TOKEN_CONTRACT_ADDRESS = os.getenv("TOKEN_CONTRACT_ADDRESS")
ESCROW_CONTRACT_ADDRESS = os.getenv("ESCROW_CONTRACT_ADDRESS")

web3 = Web3(Web3.HTTPProvider(RPC_URL))

account = web3.eth.account.from_key(PRIVATE_KEY)


# ---------- Smart Contract ABIs ----------
ABI_TOKEN = [
    {
        "inputs": [
            {"internalType": "address", "name": "recipient", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

ABI_ESCROW = [
    {
        "inputs": [
            {"internalType": "address", "name": "user", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"}
        ],
        "name": "rewardUser",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]


# ---------- Contract Instances ----------
token_contract = web3.eth.contract(
    address=web3.to_checksum_address(TOKEN_CONTRACT_ADDRESS),
    abi=ABI_TOKEN
)

escrow_contract = web3.eth.contract(
    address=web3.to_checksum_address(ESCROW_CONTRACT_ADDRESS),
    abi=ABI_ESCROW
)


# ---------- Emotion Recognition ----------
detector = FER()      # Optimized for Render (no MTCNN)


# ================================================================
#                       ROUTES
# ================================================================

# ---------- Emotion Detection API ----------
@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        data = request.json
        image_base64 = data.get("image")
        user_address = data.get("address")

        if not image_base64:
            return jsonify({"error": "No image provided"}), 400

        # Decode base64 image
        img_bytes = base64.b64decode(image_base64.split(",")[1])
        np_arr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        # Run emotion detection
        emotion, score_val = detector.top_emotion(img)
        score = int((score_val or 0) * 100)

        rewarded = False
        tx_hash = None

        # Auto reward if happy score ≥ 50 and user address exists
        if user_address and score >= 50:
            try:
                user_address = web3.to_checksum_address(user_address)

                tx = escrow_contract.functions.rewardUser(
                    user_address, 5 * 10**18
                ).build_transaction({
                    "from": account.address,
                    "gas": 300000,
                    "gasPrice": web3.to_wei("10", "gwei"),
                    "nonce": web3.eth.get_transaction_count(account.address)
                })

                signed_tx = web3.eth.account.sign_transaction(tx, PRIVATE_KEY)
                tx_hash_bytes = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
                tx_hash = tx_hash_bytes.hex()

                rewarded = True
                print(f"Reward sent → {user_address}")
                print(f"Tx → https://sepolia.etherscan.io/tx/{tx_hash}")

            except Exception as e:
                print("Reward failed:", str(e))

        return jsonify({
            "emotion": emotion or "neutral",
            "score": score,
            "rewarded": rewarded,
            "txHash": tx_hash
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500



# ---------- Manual Reward Claim ----------
@app.route("/claim-reward", methods=["POST"])
def claim_reward():
    try:
        data = request.json
        address = data.get("address")
        score = data.get("score", 0)

        if not address:
            return jsonify({"status": "error", "message": "Missing wallet address"}), 400
        if score < 250:
            return jsonify({"status": "error", "message": "Score too low"}), 400

        user_address = web3.to_checksum_address(address)

        tx = escrow_contract.functions.rewardUser(
            user_address, 5 * 10**18
        ).build_transaction({
            "from": account.address,
            "gas": 300000,
            "gasPrice": web3.to_wei("10", "gwei"),
            "nonce": web3.eth.get_transaction_count(account.address)
        })

        signed_tx = web3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)

        print(f"Reward sent to {user_address}")
        print("Tx:", tx_hash.hex())

        return jsonify({
            "status": "success",
            "txHash": tx_hash.hex()
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500



# ---------- Root Test Route ----------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "Backend Running Successfully"})


# ---------- Run Flask (Render uses Gunicorn) ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
