const express = require('express');
const { GasPrice, StargateClient, SigningStargateClient } = require('@cosmjs/stargate');
const { DirectSecp256k1HdWallet } = require('@cosmjs/proto-signing');
const { coins, coin } = require('@cosmjs/amino');

const app = express();
app.use(express.json({ limit: '10mb' }));

// Osmosis mainnet configuration with fallback endpoints
const rpcEndpoints = [
    'https://rpc.osmosis.zone',
    'https://osmosis-rpc.quickapi.com',
    'https://rpc-osmosis.blockapsis.com',
    'https://osmosis-rpc.polkachu.com',
    'https://rpc.osmosis.strange.love'
];

let currentRpcIndex = 0;
const gasPrice = GasPrice.fromString('0.025uosmo');

// Function to get next RPC endpoint on failure
function getNextRpcEndpoint() {
    currentRpcIndex = (currentRpcIndex + 1) % rpcEndpoints.length;
    const endpoint = rpcEndpoints[currentRpcIndex];
    console.log(`🔄 Switching to RPC endpoint: ${endpoint}`);
    return endpoint;
}

// Get current RPC endpoint
function getCurrentRpcEndpoint() {
    return rpcEndpoints[currentRpcIndex];
}

// Check if error is RPC-related (should retry) vs transaction-related (should not retry)
function isRpcError(error) {
    const errorStr = error.toString().toLowerCase();
    
    // RPC/Network errors that should trigger failover
    const rpcErrorPatterns = [
        'network error',
        'timeout',
        'connection',
        'econnrefused',
        'enotfound',
        'socket',
        'status code 429',  // Rate limiting
        'status code 502',  // Bad gateway
        'status code 503',  // Service unavailable
        'status code 504',  // Gateway timeout
        'bad status on response: 429',
        'failed to fetch',
        'fetch failed',
        'pool reached max tx capacity',  // Mempool congestion on specific RPC
        'mempool is full',
        'account sequence mismatch'  // Often RPC sync issues, not real sequence errors
    ];
    
    // Special case: Don't retry on genuine insufficient funds
    const transactionErrorPatterns = [
        'insufficient funds',
        'insufficient balance',
        'smaller than',
        'invalid address'
    ];
    
    // If it's definitely a transaction error, don't retry
    if (transactionErrorPatterns.some(pattern => errorStr.includes(pattern))) {
        return false;
    }
    
    // Check if it's an RPC error
    return rpcErrorPatterns.some(pattern => errorStr.includes(pattern));
}

// Retry function with RPC failover
async function executeWithRpcFailover(operation, maxRetries = 3) {
    let lastError;
    let retries = 0;
    
    while (retries < maxRetries) {
        try {
            return await operation(getCurrentRpcEndpoint());
        } catch (error) {
            lastError = error;
            console.log(`❌ Error with RPC ${getCurrentRpcEndpoint()}: ${error.message}`);
            
            // Only retry if it's an RPC error, not a transaction error
            if (isRpcError(error) && retries < maxRetries - 1) {
                console.log(`🔄 RPC error detected, switching to backup endpoint...`);
                getNextRpcEndpoint();
                retries++;
                continue;
            } else {
                // Transaction error or max retries reached - don't retry
                break;
            }
        }
    }
    
    throw lastError;
}

console.log('🚀 Starting Simple OsmoJS Multisend Service');
console.log('📡 Primary RPC Endpoint:', getCurrentRpcEndpoint());
console.log('🔄 Fallback endpoints available:', rpcEndpoints.length - 1);

// Health check endpoint
app.get('/health', (req, res) => {
    res.json({ 
        status: 'healthy', 
        service: 'simple-osmjs-multisend',
        timestamp: new Date().toISOString(),
        rpc: getCurrentRpcEndpoint(),
        fallback_rpcs_available: rpcEndpoints.length - 1
    });
});

// Get account balance
app.post('/balance', async (req, res) => {
    try {
        const { address, denom = 'uosmo' } = req.body;
        
        if (!address) {
            return res.status(400).json({ error: 'Address required' });
        }

        const result = await executeWithRpcFailover(async (rpcEndpoint) => {
            const client = await StargateClient.connect(rpcEndpoint);
            const balance = await client.getBalance(address, denom);
            await client.disconnect();
            return balance;
        });
        
        const balance = result;
        
        // Determine token symbol from denom
        let tokenSymbol = 'OSMO';
        if (balance.denom.includes('LAB')) {
            tokenSymbol = 'LAB';
        } else if (balance.denom === 'uosmo') {
            tokenSymbol = 'OSMO';
        }
        
        res.json({
            success: true,
            balance: {
                denom: balance.denom,
                amount: balance.amount,
                formatted: (parseInt(balance.amount) / 1e6).toFixed(6) + ' ' + tokenSymbol
            }
        });
        
    } catch (error) {
        console.error('❌ Balance check error:', error);
        res.status(500).json({ 
            success: false, 
            error: error.message 
        });
    }
});

// Single send transaction
app.post('/send', async (req, res) => {
    try {
        const { sender_mnemonic, recipient_address, amount, token = 'osmo', memo = '' } = req.body;
        
        if (!sender_mnemonic || !recipient_address || !amount) {
            return res.status(400).json({ 
                error: 'Missing required fields: sender_mnemonic, recipient_address, amount' 
            });
        }

        // Create wallet from mnemonic
        const wallet = await DirectSecp256k1HdWallet.fromMnemonic(sender_mnemonic, {
            prefix: 'osmo'
        });
        
        const [firstAccount] = await wallet.getAccounts();
        const senderAddress = firstAccount.address;

        // Convert amount to micro units and get proper denom
        let denom;
        if (token === 'osmo') {
            denom = 'uosmo';
        } else if (token === 'lab') {
            denom = 'factory/osmo17fel472lgzs87ekt9dvk0zqyh5gl80sqp4sk4n/LAB';
        } else {
            denom = `u${token}`;
        }
        const microAmount = Math.floor(parseFloat(amount) * 1e6).toString();
        
        // Execute transaction with RPC failover
        const result = await executeWithRpcFailover(async (rpcEndpoint) => {
            // Connect to signing client
            const client = await SigningStargateClient.connectWithSigner(
                rpcEndpoint,
                wallet,
                { gasPrice }
            );

            // Create send message
            const sendMsg = {
                typeUrl: '/cosmos.bank.v1beta1.MsgSend',
                value: {
                    fromAddress: senderAddress,
                    toAddress: recipient_address,
                    amount: coins(microAmount, denom)
                }
            };

            // Estimate gas
            const gasEstimation = await client.simulate(senderAddress, [sendMsg], memo);
            const fee = {
                amount: coins(Math.ceil(gasEstimation * 1.3 * 0.025), 'uosmo'),
                gas: Math.ceil(gasEstimation * 1.3).toString()
            };

            console.log(`📤 Sending ${amount} ${token.toUpperCase()} from ${senderAddress} to ${recipient_address}`);
            console.log(`⛽ Gas estimated: ${gasEstimation}, fee: ${fee.amount[0].amount} uosmo`);

            // Broadcast transaction
            const txResult = await client.signAndBroadcast(senderAddress, [sendMsg], fee, memo);
            
            await client.disconnect();
            return { txResult, fee };
        });

        const { txResult, fee } = result;

        if (txResult.code === 0) {
            res.json({
                success: true,
                tx_hash: txResult.transactionHash,
                height: Number(txResult.height),
                gas_used: Number(txResult.gasUsed),
                gas_wanted: Number(txResult.gasWanted),
                fee_paid: Number(fee.amount[0].amount) + ' uosmo'
            });
        } else {
            res.status(400).json({
                success: false,
                error: `Transaction failed: ${txResult.rawLog}`
            });
        }

    } catch (error) {
        console.error('❌ Send transaction error:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// Multisend transaction
app.post('/multisend', async (req, res) => {
    try {
        const { sender_mnemonic, recipients, memo = 'Multisend transaction' } = req.body;
        
        if (!sender_mnemonic || !recipients || !Array.isArray(recipients)) {
            return res.status(400).json({ 
                error: 'Missing required fields: sender_mnemonic, recipients (array)' 
            });
        }

        console.log(`📤 Processing multisend for ${recipients.length} recipients`);

        // Create wallet from mnemonic
        const wallet = await DirectSecp256k1HdWallet.fromMnemonic(sender_mnemonic, {
            prefix: 'osmo'
        });
        
        const [firstAccount] = await wallet.getAccounts();
        const senderAddress = firstAccount.address;

        console.log(`👤 Sender: ${senderAddress}`);

        // Prepare inputs and outputs for multisend
        const totalAmounts = {};
        const outputs = [];

        // Process each recipient
        for (const recipient of recipients) {
            const { address, amount, token = 'osmo' } = recipient;
            
            if (!address || !amount) {
                return res.status(400).json({ 
                    error: 'Each recipient must have address and amount' 
                });
            }

            // Get proper denom for token
            let denom;
            if (token === 'osmo') {
                denom = 'uosmo';
            } else if (token === 'lab') {
                denom = 'factory/osmo17fel472lgzs87ekt9dvk0zqyh5gl80sqp4sk4n/LAB';
            } else {
                denom = `u${token}`;
            }
            const microAmount = Math.floor(parseFloat(amount) * 1e6).toString();
            
            // Track total amounts by denom
            totalAmounts[denom] = (totalAmounts[denom] || 0) + parseInt(microAmount);
            
            outputs.push({
                address: address,
                coins: coins(microAmount, denom)
            });

            console.log(`  💰 ${address}: ${amount} ${token.toUpperCase()}`);
        }

        // Create inputs (sender's total amounts)
        const inputs = [{
            address: senderAddress,
            coins: Object.entries(totalAmounts).map(([denom, amount]) => 
                coin(amount.toString(), denom)
            )
        }];

        // Create multisend message
        const multisendMsg = {
            typeUrl: '/cosmos.bank.v1beta1.MsgMultiSend',
            value: {
                inputs: inputs,
                outputs: outputs
            }
        };

        // Execute multisend with RPC failover
        const result = await executeWithRpcFailover(async (rpcEndpoint) => {
            // Connect to signing client
            const client = await SigningStargateClient.connectWithSigner(
                rpcEndpoint,
                wallet,
                { gasPrice }
            );

            console.log('⚡ Estimating gas...');

            // Estimate gas
            const gasEstimation = await client.simulate(senderAddress, [multisendMsg], memo);
            const fee = {
                amount: coins(Math.ceil(gasEstimation * 1.4 * 0.025), 'uosmo'),
                gas: Math.ceil(gasEstimation * 1.4).toString()
            };

            console.log(`⛽ Gas estimated: ${gasEstimation}, fee: ${fee.amount[0].amount} uosmo`);
            console.log('📡 Broadcasting transaction...');

            // Broadcast transaction
            const txResult = await client.signAndBroadcast(senderAddress, [multisendMsg], fee, memo);
            
            await client.disconnect();
            return { txResult, fee };
        });

        const { txResult, fee } = result;

        if (txResult.code === 0) {
            console.log(`✅ Multisend successful! TX: ${txResult.transactionHash}`);
            res.json({
                success: true,
                tx_hash: txResult.transactionHash,
                height: Number(txResult.height),
                gas_used: Number(txResult.gasUsed),
                gas_wanted: Number(txResult.gasWanted),
                fee_paid: Number(fee.amount[0].amount) + ' uosmo',
                recipients_count: recipients.length,
                total_amounts: Object.entries(totalAmounts).map(([denom, amount]) => ({
                    denom,
                    amount: amount.toString(),
                    formatted: denom === 'uosmo' ? (amount / 1e6).toFixed(6) + ' OSMO' : amount
                }))
            });
        } else {
            console.log(`❌ Transaction failed: ${txResult.rawLog}`);
            res.status(400).json({
                success: false,
                error: `Transaction failed: ${txResult.rawLog}`
            });
        }

    } catch (error) {
        console.error('❌ Multisend transaction error:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// Duplicate /send endpoint removed - using the fixed one above

const PORT = process.env.PORT || 3001;
app.listen(PORT, () => {
    console.log(`🌐 Simple OsmoJS Multisend Service running on http://localhost:${PORT}`);
    console.log('📋 Available endpoints:');
    console.log('  GET  /health - Health check');
    console.log('  POST /send - Single token transfer');
    console.log('  POST /multisend - Multiple token transfers');
    console.log('');
    console.log('🔥 Ready to process transactions!');
});