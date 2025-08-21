/**
 * Wallet Manager for Keplr and Leap integration
 * Uses browser-compatible wallet detection and connection
 */

class WalletManager {
    constructor() {
        this.connectedWallet = null;
        this.walletType = null;
        this.address = null;
        this.chainId = 'osmosis-1';
        
        // Wallet connection state
        this.isConnecting = false;
        this.isConnected = false;
        
        // Event callbacks
        this.onConnectionChange = null;
        this.onAccountChange = null;
        this.onError = null;
        
        this.init();
    }
    
    async init() {
        // Check if wallet was previously connected
        const savedWallet = localStorage.getItem('connectedWallet');
        const savedAddress = localStorage.getItem('walletAddress');
        
        if (savedWallet && savedAddress) {
            await this.connectWallet(savedWallet, true);
        }
        
        // Listen for wallet account changes
        if (window.keplr) {
            window.addEventListener('keplr_keystorechange', () => {
                this.handleAccountChange();
            });
        }
        
        if (window.leap) {
            window.addEventListener('leap_keystorechange', () => {
                this.handleAccountChange();
            });
        }
    }
    
    async connectWallet(walletType = 'auto', isReconnection = false) {
        if (this.isConnecting) return;
        
        this.isConnecting = true;
        
        try {
            let wallet = null;
            
            // Auto-detect or use specific wallet
            if (walletType === 'auto' || walletType === 'keplr') {
                if (window.keplr) {
                    wallet = window.keplr;
                    this.walletType = 'keplr';
                }
            }
            
            if (!wallet && (walletType === 'auto' || walletType === 'leap')) {
                if (window.leap) {
                    wallet = window.leap;
                    this.walletType = 'leap';
                }
            }
            
            if (!wallet) {
                throw new Error('No compatible wallet found. Please install Keplr or Leap wallet.');
            }
            
            // Enable the chain
            await wallet.enable(this.chainId);
            
            // Get the offline signer
            const offlineSigner = wallet.getOfflineSigner(this.chainId);
            const accounts = await offlineSigner.getAccounts();
            
            if (accounts.length === 0) {
                throw new Error('No accounts found in wallet');
            }
            
            this.connectedWallet = wallet;
            this.address = accounts[0].address;
            this.isConnected = true;
            
            // Save connection state
            localStorage.setItem('connectedWallet', this.walletType);
            localStorage.setItem('walletAddress', this.address);
            
            if (!isReconnection) {
                this.fireConnectionChange(true);
            }
            
            return {
                success: true,
                address: this.address,
                walletType: this.walletType
            };
            
        } catch (error) {
            this.isConnected = false;
            this.connectedWallet = null;
            this.address = null;
            this.walletType = null;
            
            // Clear saved state on error
            localStorage.removeItem('connectedWallet');
            localStorage.removeItem('walletAddress');
            
            this.fireError(error.message);
            
            return {
                success: false,
                error: error.message
            };
        } finally {
            this.isConnecting = false;
        }
    }
    
    async disconnectWallet() {
        this.connectedWallet = null;
        this.address = null;
        this.walletType = null;
        this.isConnected = false;
        
        // Clear saved state
        localStorage.removeItem('connectedWallet');
        localStorage.removeItem('walletAddress');
        
        this.fireConnectionChange(false);
        
        return { success: true };
    }
    
    async getBalance(denom = 'uosmo') {
        if (!this.isConnected || !this.address) {
            throw new Error('Wallet not connected');
        }
        
        try {
            // Use CosmJS to query balance
            const { StargateClient } = await import('https://cdn.skypack.dev/@cosmjs/stargate');
            
            const client = await StargateClient.connect('https://lcd.osmosis.zone');
            const balance = await client.getBalance(this.address, denom);
            
            return {
                success: true,
                balance: balance
            };
        } catch (error) {
            this.fireError(`Failed to get balance: ${error.message}`);
            return {
                success: false,
                error: error.message
            };
        }
    }
    
    async signAndBroadcast(msgs, fee, memo = '') {
        if (!this.isConnected || !this.connectedWallet) {
            throw new Error('Wallet not connected');
        }
        
        try {
            // Get the offline signer
            const offlineSigner = this.connectedWallet.getOfflineSigner(this.chainId);
            
            // Use StargateClient for signing and broadcasting
            const { SigningStargateClient } = await import('https://cdn.skypack.dev/@cosmjs/stargate');
            
            const client = await SigningStargateClient.connectWithSigner(
                'https://rpc.osmosis.zone',
                offlineSigner
            );
            
            const result = await client.signAndBroadcast(this.address, msgs, fee, memo);
            
            return {
                success: true,
                transactionHash: result.transactionHash,
                height: result.height,
                gasUsed: result.gasUsed
            };
        } catch (error) {
            this.fireError(`Transaction failed: ${error.message}`);
            return {
                success: false,
                error: error.message
            };
        }
    }
    
    async simulateTransaction(msgs, fee, memo = '') {
        if (!this.isConnected || !this.connectedWallet) {
            throw new Error('Wallet not connected');
        }
        
        try {
            const offlineSigner = this.connectedWallet.getOfflineSigner(this.chainId);
            const { SigningStargateClient } = await import('https://cdn.skypack.dev/@cosmjs/stargate');
            
            const client = await SigningStargateClient.connectWithSigner(
                'https://rpc.osmosis.zone',
                offlineSigner
            );
            
            const gasEstimate = await client.simulate(this.address, msgs, memo);
            
            return {
                success: true,
                gasEstimate: gasEstimate
            };
        } catch (error) {
            return {
                success: false,
                error: error.message
            };
        }
    }
    
    formatAddress(address = this.address) {
        if (!address) return '';
        return `${address.slice(0, 10)}...${address.slice(-8)}`;
    }
    
    getConnectionStatus() {
        return {
            isConnected: this.isConnected,
            address: this.address,
            walletType: this.walletType,
            formattedAddress: this.formatAddress()
        };
    }
    
    // Event handlers
    handleAccountChange() {
        if (this.onAccountChange) {
            this.onAccountChange();
        }
        // Refresh connection
        if (this.isConnected) {
            this.connectWallet(this.walletType, true);
        }
    }
    
    fireConnectionChange(connected) {
        if (this.onConnectionChange) {
            this.onConnectionChange(connected, this.getConnectionStatus());
        }
    }
    
    fireError(message) {
        if (this.onError) {
            this.onError(message);
        }
        console.error('Wallet Error:', message);
    }
    
    // Event listener setters
    setOnConnectionChange(callback) {
        this.onConnectionChange = callback;
    }
    
    setOnAccountChange(callback) {
        this.onAccountChange = callback;
    }
    
    setOnError(callback) {
        this.onError = callback;
    }
}

// Create global wallet manager instance
window.walletManager = new WalletManager();