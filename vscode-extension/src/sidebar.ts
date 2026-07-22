import * as vscode from 'vscode';
import { CodeNexusService } from './service';

export class CodeNexusSidebarProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'codenexus.sidebar';
    private _view?: vscode.WebviewView;

    constructor(
        private readonly _extensionUri: vscode.Uri,
        private readonly _service: CodeNexusService
    ) {}

    public resolveWebviewView(
        webviewView: vscode.WebviewView,
        context: vscode.WebviewViewResolveContext,
        _token: vscode.CancellationToken
    ) {
        this._view = webviewView;

        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this._extensionUri]
        };

        webviewView.webview.html = this._getHtmlForWebview();

        // Handle messages from webview
        webviewView.webview.onDidReceiveMessage(async (message) => {
            switch (message.type) {
                case 'index':
                    await this._service.indexWorkspace();
                    this._updateWebview();
                    break;
                case 'search':
                    const results = await this._service.search(message.query);
                    this._view?.webview.postMessage({ type: 'results', results });
                    break;
                case 'clear':
                    await this._service.clearIndex();
                    this._updateWebview();
                    break;
            }
        });

        // Initial update
        this._updateWebview();
    }

    private async _updateWebview() {
        if (this._view) {
            const status = await this._service.getStatus();
            this._view.webview.postMessage({ type: 'status', status });
        }
    }

    private _getHtmlForWebview() {
        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CodeNexus</title>
    <style>
        body {
            font-family: var(--vscode-font-family);
            font-size: var(--vscode-font-size);
            color: var(--vscode-foreground);
            padding: 10px;
        }
        .status {
            margin-bottom: 15px;
            padding: 10px;
            background: var(--vscode-sideBar-background);
            border-radius: 5px;
        }
        .stat {
            display: flex;
            justify-content: space-between;
            margin: 5px 0;
        }
        .stat-label {
            color: var(--vscode-descriptionForeground);
        }
        .stat-value {
            font-weight: bold;
        }
        button {
            width: 100%;
            padding: 8px;
            margin: 5px 0;
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            border-radius: 3px;
            cursor: pointer;
        }
        button:hover {
            background: var(--vscode-button-hoverBackground);
        }
        input {
            width: 100%;
            padding: 8px;
            margin: 5px 0;
            background: var(--vscode-input-background);
            color: var(--vscode-input-foreground);
            border: 1px solid var(--vscode-input-border);
            border-radius: 3px;
        }
        .results {
            margin-top: 10px;
        }
        .result-item {
            padding: 8px;
            margin: 5px 0;
            background: var(--vscode-sideBarSectionHeader-background);
            border-radius: 3px;
            cursor: pointer;
        }
        .result-item:hover {
            background: var(--vscode-list-hoverBackground);
        }
    </style>
</head>
<body>
    <div class="status">
        <h3>CodeNexus Status</h3>
        <div class="stat">
            <span class="stat-label">Nodes:</span>
            <span class="stat-value" id="nodes">0</span>
        </div>
        <div class="stat">
            <span class="stat-label">Edges:</span>
            <span class="stat-value" id="edges">0</span>
        </div>
        <div class="stat">
            <span class="stat-label">Files:</span>
            <span class="stat-value" id="files">0</span>
        </div>
    </div>

    <button id="indexBtn">Index Workspace</button>
    <button id="clearBtn">Clear Index</button>

    <input type="text" id="searchInput" placeholder="Search context..." />
    <button id="searchBtn">Search</button>

    <div class="results" id="results"></div>

    <script>
        const vscode = acquireVsCodeApi();
        
        document.getElementById('indexBtn').addEventListener('click', () => {
            vscode.postMessage({ type: 'index' });
        });

        document.getElementById('clearBtn').addEventListener('click', () => {
            vscode.postMessage({ type: 'clear' });
        });

        document.getElementById('searchBtn').addEventListener('click', () => {
            const query = document.getElementById('searchInput').value;
            vscode.postMessage({ type: 'search', query });
        });

        document.getElementById('searchInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                const query = e.target.value;
                vscode.postMessage({ type: 'search', query });
            }
        });

        window.addEventListener('message', (event) => {
            const message = event.data;
            
            if (message.type === 'status') {
                document.getElementById('nodes').textContent = message.status.nodes;
                document.getElementById('edges').textContent = message.status.edges;
                document.getElementById('files').textContent = message.status.files;
            }
            
            if (message.type === 'results') {
                const resultsDiv = document.getElementById('results');
                resultsDiv.innerHTML = '';
                
                message.results.forEach(result => {
                    const div = document.createElement('div');
                    div.className = 'result-item';
                    div.innerHTML = \`
                        <strong>\${result.name}</strong><br>
                        <small>\${result.file} - \${result.type}</small><br>
                        <small>Score: \${result.score.toFixed(4)}</small>
                    \`;
                    resultsDiv.appendChild(div);
                });
            }
        });
    </script>
</body>
</html>`;
    }
}
