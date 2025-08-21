/**
 * Network Diagnostics for Osmosis Connectivity
 * Helps diagnose network issues with various Osmosis endpoints
 */

class NetworkDiagnostics {
    constructor() {
        this.endpoints = [
            { name: 'Polkachu API', url: 'https://osmosis-api.polkachu.com', type: 'REST' },
            { name: 'Polkachu RPC', url: 'https://osmosis-rpc.polkachu.com', type: 'RPC' },
            { name: 'Official LCD', url: 'https://lcd.osmosis.zone', type: 'REST' },
            { name: 'EcoStake REST', url: 'https://rest-osmosis.ecostake.com', type: 'REST' },
            { name: 'Keplr LCD', url: 'https://lcd-osmosis.keplr.app', type: 'REST' }
        ];
    }

    async testConnectivity() {
        console.log('🔬 Running Osmosis network diagnostics...');
        
        const results = [];
        
        for (const endpoint of this.endpoints) {
            const result = await this.testEndpoint(endpoint);
            results.push(result);
            
            const status = result.success ? '✅' : '❌';
            console.log(`${status} ${endpoint.name} (${endpoint.type}): ${result.message}`);
        }
        
        return results;
    }

    async testEndpoint(endpoint) {
        const startTime = Date.now();
        
        try {
            // Test basic connectivity with node info endpoint
            const testUrl = endpoint.type === 'RPC' 
                ? `${endpoint.url}/status`
                : `${endpoint.url}/cosmos/base/tendermint/v1beta1/node_info`;
            
            const response = await fetch(testUrl, {
                method: 'GET',
                headers: { 'Accept': 'application/json' },
                signal: AbortSignal.timeout(10000) // 10 second timeout
            });
            
            const duration = Date.now() - startTime;
            
            if (response.ok) {
                return {
                    endpoint: endpoint.name,
                    url: endpoint.url,
                    type: endpoint.type,
                    success: true,
                    duration: duration,
                    message: `OK (${duration}ms)`
                };
            } else {
                return {
                    endpoint: endpoint.name,
                    url: endpoint.url,
                    type: endpoint.type,
                    success: false,
                    duration: duration,
                    message: `HTTP ${response.status} (${duration}ms)`
                };
            }
        } catch (error) {
            const duration = Date.now() - startTime;
            return {
                endpoint: endpoint.name,
                url: endpoint.url,
                type: endpoint.type,
                success: false,
                duration: duration,
                message: `Error: ${error.message} (${duration}ms)`
            };
        }
    }

    async testWalletConnectivity() {
        console.log('👛 Testing wallet provider connectivity...');
        
        if (!window.keplrWallet || !window.keplrWallet.isWalletConnected()) {
            return { success: false, message: 'No wallet connected' };
        }

        try {
            // Test wallet balance fetch
            const address = window.keplrWallet.getAddress();
            console.log(`Testing balance fetch for address: ${address}`);
            
            await window.keplrWallet.updateBalance();
            const balance = window.keplrWallet.getBalance();
            
            return { 
                success: true, 
                message: `Wallet connected (Balance: ${balance} OSMO)`,
                address: address,
                balance: balance
            };
        } catch (error) {
            return { 
                success: false, 
                message: `Wallet connectivity error: ${error.message}` 
            };
        }
    }

    async runFullDiagnostics() {
        console.log('🩺 Running full network diagnostics...');
        
        const networkResults = await this.testConnectivity();
        const walletResult = await this.testWalletConnectivity();
        
        const workingEndpoints = networkResults.filter(r => r.success);
        const failingEndpoints = networkResults.filter(r => !r.success);
        
        const report = {
            timestamp: new Date().toISOString(),
            summary: {
                totalEndpoints: networkResults.length,
                workingEndpoints: workingEndpoints.length,
                failingEndpoints: failingEndpoints.length,
                walletConnected: walletResult.success
            },
            networkResults: networkResults,
            walletResult: walletResult,
            recommendations: this.generateRecommendations(networkResults, walletResult)
        };
        
        console.log('📊 Diagnostics complete:', report);
        return report;
    }

    generateRecommendations(networkResults, walletResult) {
        const recommendations = [];
        
        const workingCount = networkResults.filter(r => r.success).length;
        
        if (workingCount === 0) {
            recommendations.push('🔴 Critical: No Osmosis endpoints accessible. Check internet connection.');
        } else if (workingCount < 3) {
            recommendations.push('🟡 Warning: Limited endpoint connectivity. Some features may be unreliable.');
        } else {
            recommendations.push('🟢 Good: Multiple endpoints working normally.');
        }
        
        if (!walletResult.success) {
            recommendations.push('👛 Connect your Keplr or Leap wallet to enable betting.');
        }
        
        // Check for specific endpoint issues
        const keplrLcd = networkResults.find(r => r.endpoint === 'Keplr LCD');
        if (keplrLcd && !keplrLcd.success) {
            recommendations.push('⚠️ Keplr LCD endpoint down - using alternative endpoints.');
        }
        
        return recommendations;
    }

    // Utility method to show diagnostics in UI
    showDiagnosticsModal(report) {
        const modal = document.createElement('div');
        modal.style.cssText = `
            position: fixed; top: 0; left: 0; width: 100%; height: 100%; 
            background: rgba(0, 0, 0, 0.7); z-index: 10000; 
            display: flex; justify-content: center; align-items: center; 
            padding: 20px;
        `;
        
        const content = document.createElement('div');
        content.style.cssText = `
            background: var(--card-bg); border: 1px solid var(--border-color); 
            border-radius: 12px; max-width: 600px; width: 100%; 
            max-height: 80vh; overflow-y: auto; padding: 1.5rem;
            color: var(--text-primary);
        `;
        
        content.innerHTML = `
            <div style="display: flex; justify-content: between; align-items: center; margin-bottom: 1rem;">
                <h4><i class="fas fa-network-wired"></i> Network Diagnostics</h4>
                <button onclick="this.closest('[style*=fixed]').remove()" style="background: none; border: none; color: var(--text-secondary); font-size: 1.5rem; cursor: pointer;">×</button>
            </div>
            
            <div style="margin-bottom: 1rem;">
                <strong>Summary:</strong><br>
                ${report.summary.workingEndpoints}/${report.summary.totalEndpoints} endpoints working<br>
                Wallet: ${report.walletResult.success ? '✅ Connected' : '❌ Not connected'}
            </div>
            
            <div style="margin-bottom: 1rem;">
                <strong>Recommendations:</strong>
                <ul style="margin: 0.5rem 0; padding-left: 1.5rem;">
                    ${report.recommendations.map(rec => `<li>${rec}</li>`).join('')}
                </ul>
            </div>
            
            <div style="margin-bottom: 1rem;">
                <strong>Endpoint Status:</strong><br>
                ${report.networkResults.map(result => {
                    const status = result.success ? '✅' : '❌';
                    return `<div style="font-family: monospace; font-size: 0.9rem; margin: 0.25rem 0;">
                        ${status} ${result.endpoint}: ${result.message}
                    </div>`;
                }).join('')}
            </div>
            
            <div style="text-align: center;">
                <button onclick="this.closest('[style*=fixed]').remove()" class="btn btn-secondary">Close</button>
            </div>
        `;
        
        modal.appendChild(content);
        document.body.appendChild(modal);
    }
}

// Initialize diagnostics
window.networkDiagnostics = new NetworkDiagnostics();

// Auto-run diagnostics on errors
window.addEventListener('error', (event) => {
    if (event.message.includes('fetch') || event.message.includes('network')) {
        console.warn('🩺 Network error detected, running diagnostics...');
        window.networkDiagnostics.runFullDiagnostics();
    }
});

// Add global method to run diagnostics manually
window.runDiagnostics = async () => {
    const report = await window.networkDiagnostics.runFullDiagnostics();
    window.networkDiagnostics.showDiagnosticsModal(report);
};