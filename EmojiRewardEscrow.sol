// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IEMOJO {
    function transfer(address recipient, uint256 amount) external returns (bool);
    function transferFrom(address sender, address recipient, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/**
 * @title EMOJOEscrow
 * @notice Escrow contract that stores EMOJO tokens and rewards winners automatically.
 */
contract EMOJOEscrow {
    address public owner;
    IEMOJO public token;

    event RewardSent(address indexed user, uint256 amount);
    event Deposit(address indexed from, uint256 amount);
    event Withdraw(address indexed to, uint256 amount);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not authorized");
        _;
    }

    constructor(address _token) {
        require(_token != address(0), "Invalid token address");
        token = IEMOJO(_token);
        owner = msg.sender;
    }

    /// @notice Deposit EMOJO tokens into escrow (requires approve() first)
    function deposit(uint256 amount) external onlyOwner {
        require(token.transferFrom(msg.sender, address(this), amount), "Transfer failed");
        emit Deposit(msg.sender, amount);
    }

    /// @notice Reward a user with EMOJO tokens (default 5)
    function rewardUser(address user, uint256 amount) external onlyOwner {
        require(user != address(0), "Invalid address");
        require(token.balanceOf(address(this)) >= amount, "Insufficient balance");

        bool sent = token.transfer(user, amount);
        require(sent, "Reward failed");
        emit RewardSent(user, amount);
    }

    /// @notice Withdraw leftover tokens
    function withdraw(uint256 amount) external onlyOwner {
        require(token.balanceOf(address(this)) >= amount, "Insufficient tokens");
        bool sent = token.transfer(owner, amount);
        require(sent, "Withdraw failed");
        emit Withdraw(owner, amount);
    }

    /// @notice Check escrow balance
    function escrowBalance() external view returns (uint256) {
        return token.balanceOf(address(this));
    }
}
