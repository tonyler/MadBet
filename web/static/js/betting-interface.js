/**
 * Enhanced Betting Interface that integrates with existing wallet system
 */

class BettingInterface {
    constructor() {
        this.selectedBet = null;
        this.selectedOption = null;
        this.betAmount = 0;
        this.token = 'osmo';
        this.userBets = new Map(); // Track user's existing bets
        this.currentWalletAddress = null; // Track current wallet address
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        
        // Listen to existing wallet events (maintain compatibility)
        window.addEventListener('keplr_connected', (e) => {
            this.onWalletConnected(e.detail);
        });
        
        window.addEventListener('keplr_disconnected', () => {
            this.onWalletDisconnected();
        });
        
        // Check existing bets when page loads
        setTimeout(() => {
            this.checkExistingBets();
        }, 1000);
    }
    
    setupEventListeners() {
        // Place bet buttons
        document.addEventListener('click', (e) => {
            if (e.target.matches('[data-place-bet]') || e.target.closest('[data-place-bet]')) {
                e.preventDefault();
                e.stopPropagation();
                
                const button = e.target.closest('[data-place-bet]') || e.target;
                const betId = button.dataset.betId;
                const optionIndex = parseInt(button.dataset.optionIndex);
                const optionText = button.dataset.optionText;
                const betAmount = parseFloat(button.dataset.betAmount);
                const betToken = button.dataset.betToken;
                
                this.openBetModal(betId, optionIndex, optionText, betAmount, betToken);
            }
            
            if (e.target.matches('[data-submit-bet]')) {
                this.submitBet();
            }
            
            if (e.target.matches('[data-close-modal]')) {
                this.closeBetModal();
            }
        });
        
        // Bet amount input
        document.addEventListener('input', (e) => {
            if (e.target.matches('[name="bet-amount"]')) {
                this.betAmount = parseFloat(e.target.value) || 0;
                this.updateBetUI();
            }
        });
    }
    
    openBetModal(betId, optionIndex, optionText, betAmount, betToken) {
        // Check if wallet is connected using existing system
        if (!window.keplrWallet || !window.keplrWallet.isWalletConnected()) {
            this.showError('Please connect your wallet first');
            return;
        }
        
        // Check if user already bet on this bet
        if (this.userBets.has(betId)) {
            this.showError('You have already placed a bet on this question');
            return;
        }
        
        // Store bet details
        this.selectedBet = {
            id: betId,
            optionIndex: optionIndex,
            optionText: optionText,
            amount: betAmount,
            token: betToken
        };
        
        this.betAmount = betAmount; // Set the fixed amount
        
        // Update modal content
        this.updateModalContent();
        
        // Show modal
        const modal = document.querySelector('[data-bet-modal]');
        if (modal) {
            modal.style.display = 'block';
        }
    }
    
    updateModalContent() {
        if (!this.selectedBet) return;
        
        // Update bet option display
        const optionDisplay = document.querySelector('[data-bet-option-display]');
        if (optionDisplay) {
            optionDisplay.innerHTML = `
                <strong>Option ${this.selectedBet.optionIndex + 1}:</strong> ${this.selectedBet.optionText}<br>
                <small>Amount: ${this.selectedBet.amount} ${this.selectedBet.token.toUpperCase()}</small>
            `;
        }
        
        // Update wallet status
        const statusContainer = document.querySelector('[data-wallet-status-container]');
        if (statusContainer) {
            if (window.keplrWallet && window.keplrWallet.isWalletConnected()) {
                statusContainer.innerHTML = `
                    <div style="background: rgba(0, 255, 136, 0.1); border: 1px solid rgba(0, 255, 136, 0.3); color: var(--success); padding: 1rem; border-radius: 8px; margin-bottom: 1rem;">
                        <i class="fas fa-check-circle"></i> Wallet connected: ${window.keplrWallet.getAddress().substring(0, 10)}...
                    </div>
                `;
            } else {
                statusContainer.innerHTML = `
                    <div style="background: rgba(255, 170, 0, 0.1); border: 1px solid rgba(255, 170, 0, 0.3); color: var(--warning); padding: 1rem; border-radius: 8px; margin-bottom: 1rem;">
                        <i class="fas fa-exclamation-triangle"></i> Please connect your wallet first
                    </div>
                `;
            }
        }
        
        // Update bet amount input
        const amountInput = document.querySelector('[name="bet-amount"]');
        if (amountInput) {
            amountInput.value = this.selectedBet.amount;
            amountInput.readOnly = true; // Fixed amount betting
        }
        
        // Update balance display
        const balanceElement = document.querySelector('[data-wallet-balance]');
        if (balanceElement && window.keplrWallet && window.keplrWallet.isWalletConnected()) {
            const balance = window.keplrWallet.getBalance();
            balanceElement.textContent = `${balance} OSMO`;
        }
        
        this.updateBetUI();
    }
    
    closeBetModal() {
        const modal = document.querySelector('[data-bet-modal]');
        if (modal) {
            modal.style.display = 'none';
        }
        this.selectedBet = null;
        this.betAmount = 0;
    }
    
    updateBetUI() {
        const submitButton = document.querySelector('[data-submit-bet]');
        if (submitButton && this.selectedBet) {
            const walletConnected = window.keplrWallet && window.keplrWallet.isWalletConnected();
            const hasEnoughBalance = walletConnected && parseFloat(window.keplrWallet.getBalance()) >= this.selectedBet.amount;
            
            submitButton.disabled = !walletConnected || !hasEnoughBalance;
            
            if (!walletConnected) {
                submitButton.innerHTML = '<i class="fas fa-wallet"></i> Connect Wallet';
            } else if (!hasEnoughBalance) {
                submitButton.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Insufficient Balance';
                submitButton.className = 'btn btn-warning';
            } else {
                submitButton.innerHTML = '<i class="fas fa-check"></i> Confirm Bet';
                submitButton.className = 'btn btn-success';
            }
        }
    }
    
    async submitBet() {
        if (!window.keplrWallet || !window.keplrWallet.isWalletConnected()) {
            this.showError('Wallet not connected');
            return;
        }
        
        if (!this.selectedBet) {
            this.showError('No bet selected');
            return;
        }
        
        this.showInfo('Processing bet...');
        
        const statusDiv = document.querySelector('[data-transaction-status]');
        const submitBtn = document.querySelector('[data-submit-bet]');
        
        try {
            // Show transaction status
            if (statusDiv) {
                statusDiv.style.display = 'block';
                statusDiv.innerHTML = `
                    <div style="background: rgba(0, 170, 255, 0.1); border: 1px solid rgba(0, 170, 255, 0.3); color: var(--info); padding: 1rem; border-radius: 8px;">
                        <i class="fas fa-spinner fa-spin"></i> Preparing transaction...
                    </div>
                `;
            }
            
            if (submitBtn) submitBtn.disabled = true;
            
            // Create transaction memo
            const memo = `Bet #${this.selectedBet.id} - Option ${this.selectedBet.optionIndex + 1}: ${this.selectedBet.optionText}`;
            
            // Real escrow address for betting funds - a proper Osmosis address for bet escrow
            // This should be replaced with your actual betting contract or escrow address
            const escrowAddress = 'osmo166pj4whqgtcdgnuv9qh2xmwvh4v7v93l5p9zvt';
            
            // Update status to show transaction creation
            if (statusDiv) {
                statusDiv.innerHTML = `
                    <div style="background: rgba(0, 170, 255, 0.1); border: 1px solid rgba(0, 170, 255, 0.3); color: var(--info); padding: 1rem; border-radius: 8px;">
                        <i class="fas fa-coins"></i> Creating real on-chain transaction...
                    </div>
                `;
            }
            
            // Create real on-chain transaction
            let transactionResult;
            try {
                transactionResult = await window.keplrWallet.createBetTransaction(
                    escrowAddress,
                    this.selectedBet.amount,
                    memo
                );
                
                console.log('✅ Real transaction created successfully:', transactionResult);
                
                // Verify the transaction on-chain
                if (statusDiv) {
                    statusDiv.innerHTML = `
                        <div style="background: rgba(0, 170, 255, 0.1); border: 1px solid rgba(0, 170, 255, 0.3); color: var(--info); padding: 1rem; border-radius: 8px;">
                            <i class="fas fa-search"></i> Verifying transaction on Osmosis blockchain...
                        </div>
                    `;
                }
                
                // Verify transaction after a short delay
                setTimeout(async () => {
                    try {
                        const verification = await window.keplrWallet.verifyTransaction(transactionResult.transactionHash);
                        if (verification.verified) {
                            console.log('✅ Transaction verified on-chain:', verification);
                        } else {
                            console.warn('⚠️ Transaction verification failed:', verification.reason);
                        }
                    } catch (verifyError) {
                        console.warn('⚠️ Could not verify transaction:', verifyError.message);
                    }
                }, 3000);
                
            } catch (txError) {
                console.error('❌ Real transaction failed:', txError.message);
                
                // Provide helpful error messages based on error type
                let errorMessage = txError.message;
                let suggestion = '';
                
                if (errorMessage.includes('user rejected') || errorMessage.includes('User rejected')) {
                    errorMessage = 'Transaction cancelled by user';
                    suggestion = 'Please try again and approve the transaction in your wallet.';
                } else if (errorMessage.includes('insufficient funds') || errorMessage.includes('Insufficient funds')) {
                    errorMessage = 'Insufficient OSMO balance';
                    suggestion = 'Please add more OSMO to your wallet or reduce the bet amount.';
                } else if (errorMessage.includes('gas') || errorMessage.includes('Gas')) {
                    errorMessage = 'Transaction gas estimation failed';
                    suggestion = 'Please try again or check network connectivity.';
                } else if (errorMessage.includes('network') || errorMessage.includes('Network')) {
                    errorMessage = 'Network connection error';
                    suggestion = 'Please check your internet connection and try again.';
                } else if (errorMessage.includes('does not support')) {
                    errorMessage = 'Wallet does not support transaction signing';
                    suggestion = 'Please update your wallet extension or try a different wallet.';
                } else {
                    suggestion = 'Please ensure you have OSMO tokens and good network connectivity.';
                }
                
                // Show detailed error to user
                if (statusDiv) {
                    statusDiv.innerHTML = `
                        <div style="background: rgba(255, 68, 87, 0.1); border: 1px solid rgba(255, 68, 87, 0.3); color: var(--error); padding: 1rem; border-radius: 8px;">
                            <i class="fas fa-exclamation-triangle"></i> <strong>Transaction Failed</strong><br>
                            <small>${errorMessage}</small><br>
                            ${suggestion ? `<small class="mt-1 d-block"><strong>💡 ${suggestion}</strong></small>` : ''}
                        </div>
                    `;
                }
                
                // Re-enable submit button and return
                if (submitBtn) submitBtn.disabled = false;
                return;
            }
            
            // Record bet on backend
            const betData = {
                bet_id: this.selectedBet.id,
                option_index: this.selectedBet.optionIndex,
                wallet_address: window.keplrWallet.getAddress(),
                amount: this.selectedBet.amount,
                token: this.selectedBet.token,
                tx_hash: transactionResult.transactionHash,
                block_height: transactionResult.height || 0,
                gas_used: transactionResult.gasUsed || '0'
                // simulation parameter removed - all transactions are real
            };
            
            const response = await fetch('/api/place-bet', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(betData)
            });
            
            const result = await response.json();
            
            if (result.success) {
                // Show success with transaction details
                if (statusDiv) {
                    statusDiv.innerHTML = `
                        <div style="background: rgba(0, 255, 136, 0.1); border: 1px solid rgba(0, 255, 136, 0.3); color: var(--success); padding: 1rem; border-radius: 8px;">
                            <i class="fas fa-check-circle"></i> Real on-chain bet placed!<br>
                            <small>TX Hash: ${transactionResult.transactionHash}</small><br>
                            <small><strong>✅ Real OSMO tokens transferred to escrow</strong></small>
                        </div>
                    `;
                }
                
                // Mark user's bet
                this.markUserBet(this.selectedBet.id, this.selectedBet.optionIndex);
                
                // Close modal after delay
                setTimeout(() => {
                    this.closeBetModal();
                    // Refresh balance after real transaction
                    if (window.keplrWallet) {
                        window.keplrWallet.refreshBalance();
                    }
                }, 3000);
                
            } else {
                throw new Error(result.error || 'Failed to record bet');
            }
            
        } catch (error) {
            console.error('Bet submission failed:', error);
            
            if (statusDiv) {
                statusDiv.innerHTML = `
                    <div style="background: rgba(255, 68, 87, 0.1); border: 1px solid rgba(255, 68, 87, 0.3); color: var(--error); padding: 1rem; border-radius: 8px;">
                        <i class="fas fa-exclamation-triangle"></i> Transaction failed<br>
                        <small>${error.message}</small>
                    </div>
                `;
            }
            
            if (submitBtn) submitBtn.disabled = false;
        }
    }
    
    markUserBet(betId, optionIndex) {
        // Store user's bet
        this.userBets.set(betId, optionIndex);
        
        // Update UI to show user's bet
        const betButtons = document.querySelectorAll(`[data-bet-id="${betId}"]`);
        betButtons.forEach(button => {
            const buttonOptionIndex = parseInt(button.dataset.optionIndex);
            
            if (buttonOptionIndex === optionIndex) {
                // User's chosen option
                button.innerHTML = '<i class="fas fa-check-circle"></i> Your Bet';
                button.className = 'btn btn-sm btn-outline-success';
            } else {
                // Other options
                button.innerHTML = '<i class="fas fa-ban"></i> Already Bet';
                button.className = 'btn btn-sm btn-outline-secondary';
            }
            
            button.disabled = true;
        });
        
        // Highlight the chosen option
        const optionElement = document.getElementById(`bet-option-${betId}-${optionIndex}`);
        if (optionElement) {
            optionElement.style.border = '2px solid var(--success)';
            optionElement.style.background = 'rgba(0, 255, 136, 0.1)';
        }
    }
    
    async checkExistingBets() {
        if (!window.keplrWallet || !window.keplrWallet.isWalletConnected()) {
            return;
        }
        
        try {
            const userAddress = window.keplrWallet.getAddress();
            const response = await fetch(`/api/user-bets/${userAddress}`);
            const userBets = await response.json();
            
            if (response.ok) {
                userBets.forEach(bet => {
                    this.markUserBet(bet.bet_id, bet.option_index);
                });
            }
        } catch (error) {
            console.error('Failed to check existing bets:', error);
        }
    }
    
    onWalletConnected(detail) {
        console.log('Wallet connected:', detail);
        
        // Get current wallet address
        const newAddress = window.keplrWallet ? window.keplrWallet.getAddress() : null;
        
        // Check if this is explicitly marked as an address change or if addresses differ
        const isAddressChange = detail?.addressChanged || (this.currentWalletAddress && this.currentWalletAddress !== newAddress);
        
        if (isAddressChange) {
            console.log(`🔄 Wallet address changed from ${this.currentWalletAddress} to ${newAddress}`);
            this.handleWalletAddressChange(newAddress);
        } else {
            console.log(`👛 Wallet connected with address: ${newAddress}`);
            this.currentWalletAddress = newAddress;
        }
        
        // Check existing bets for this wallet
        this.checkExistingBets();
        
        // Update button states
        document.querySelectorAll('[data-place-bet]').forEach(btn => {
            if (!btn.disabled) {
                btn.style.opacity = '1';
            }
        });
    }
    
    handleWalletAddressChange(newAddress) {
        console.log(`🔄 Handling wallet address change to: ${newAddress}`);
        
        // Show notification to user
        const shortOldAddress = this.currentWalletAddress ? `${this.currentWalletAddress.slice(0, 8)}...` : 'previous';
        const shortNewAddress = newAddress ? `${newAddress.slice(0, 8)}...` : 'new';
        this.showInfo(`Wallet changed from ${shortOldAddress} to ${shortNewAddress}. Bet history reset.`);
        
        // Clear cached user bets (since it's a different wallet)
        this.userBets.clear();
        console.log('🗑️ Cleared cached user bets for address change');
        
        // Reset all bet buttons to their original state
        this.resetAllBetButtons();
        
        // Update current wallet address
        this.currentWalletAddress = newAddress;
        
        console.log('✅ Wallet address change handled successfully');
    }
    
    resetAllBetButtons() {
        console.log('🔄 Resetting all bet buttons to original state');
        
        // Find all bet buttons and reset them
        document.querySelectorAll('[data-place-bet]').forEach(button => {
            const betAmount = button.dataset.betAmount;
            const betToken = button.dataset.betToken;
            
            // Reset button appearance
            button.disabled = false;
            button.className = 'btn btn-sm btn-success place-bet-btn';
            button.innerHTML = `<i class="fas fa-coins"></i> Bet ${betAmount} ${betToken ? betToken.toUpperCase() : 'OSMO'}`;
            button.style.opacity = '1';
        });
        
        // Reset visual indicators on bet options
        document.querySelectorAll('[id^="bet-option-"]').forEach(option => {
            // Reset styling
            option.style.border = '';
            option.style.background = '';
            
            // Hide bet indicators
            const indicator = option.querySelector('.user-bet-indicator');
            if (indicator) {
                indicator.style.display = 'none';
                indicator.textContent = '';
            }
        });
        
        console.log('✅ All bet buttons and indicators reset');
    }
    
    onWalletDisconnected() {
        console.log('Wallet disconnected');
        
        // Clear current wallet address
        this.currentWalletAddress = null;
        
        // Clear user bets
        this.userBets.clear();
        
        // Reset all betting buttons using the common method
        this.resetAllBetButtons();
        
        // Dim betting buttons (but keep them clickable to prompt connection)
        document.querySelectorAll('[data-place-bet]').forEach(btn => {
            btn.style.opacity = '0.7';
        });
    }
    
    // UI feedback methods
    showSuccess(message) {
        this.showNotification(message, 'success');
    }
    
    showError(message) {
        this.showNotification(message, 'error');
    }
    
    showInfo(message) {
        this.showNotification(message, 'info');
    }
    
    showNotification(message, type = 'info') {
        // Create notification element if it doesn't exist
        let notification = document.querySelector('[data-notification]');
        if (!notification) {
            notification = document.createElement('div');
            notification.setAttribute('data-notification', '');
            notification.style.cssText = `
                position: fixed;
                top: 80px;
                right: 20px;
                padding: 12px 16px;
                border-radius: 8px;
                color: white;
                z-index: 1000;
                max-width: 300px;
                transition: opacity 0.3s ease;
                font-weight: 500;
            `;
            document.body.appendChild(notification);
        }
        
        // Set color based on type
        const colors = {
            success: 'linear-gradient(135deg, #00ff88, #00cc6a)',
            error: 'linear-gradient(135deg, #ff4757, #e53e3e)',
            info: 'linear-gradient(135deg, #00fff0, #9945ff)'
        };
        
        notification.style.background = colors[type] || colors.info;
        notification.textContent = message;
        notification.style.opacity = '1';
        
        // Auto-hide after 4 seconds
        setTimeout(() => {
            notification.style.opacity = '0';
        }, 4000);
    }
}

// Initialize betting interface when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.bettingInterface = new BettingInterface();
});