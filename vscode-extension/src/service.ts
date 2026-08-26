import * as vscode from 'vscode';
import * as path from 'path';
import { spawn, ChildProcess } from 'child_process';

export interface SearchResult {
    name: string;
    file: string;
    type: string;
    score: number;
    line: number;
}

export interface StatusInfo {
    nodes: number;
    edges: number;
    files: number;
}

export class CodeNexusService {
    private process: ChildProcess | null = null;
    private outputChannel: vscode.OutputChannel;
    private reindexTimer: NodeJS.Timeout | null = null;

    constructor() {
        this.outputChannel = vscode.window.createOutputChannel('CodeNexus');
    }

    isSupportedFile(fileName: string): boolean {
        const extensions = ['.py', '.js', '.jsx', '.ts', '.tsx', '.go', '.rs', '.java', '.cs'];
        return extensions.some(ext => fileName.endsWith(ext));
    }

    /**
     * Spawn codenexus with safely quoted arguments.
     * shell:true is required to resolve the pip-installed launcher on
     * Windows, so every argument must be quoted explicitly.
     */
    private spawnCli(args: string[], cwd: string, onDone: (code: number | null, stdout: string) => void): void {
        const quoted = args.map(a => (/^[\w.,:/\\-]+$/.test(a) ? a : `"${a.replace(/"/g, '\\"')}"`));
        const child = spawn('codenexus', quoted, { cwd, shell: true });

        let stdout = '';
        child.stdout?.on('data', d => { stdout += d.toString(); });
        child.stderr?.on('data', d => { this.outputChannel.append(d.toString()); });
        child.on('close', code => onDone(code, stdout));
        child.on('error', err => {
            this.outputChannel.appendLine(`codenexus not found: ${err.message}`);
            onDone(-1, '');
        });
    }

    async indexWorkspace(): Promise<void> {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceFolder) {
            vscode.window.showErrorMessage('No workspace folder found');
            return;
        }

        return new Promise((resolve, reject) => {
            this.spawnCli(['index'], workspaceFolder.uri.fsPath, (code, output) => {
                this.outputChannel.appendLine(output);
                if (code === 0) {
                    resolve();
                } else {
                    reject(new Error(`Indexing failed with code ${code}`));
                }
            });
        });
    }

    /**
     * Debounced incremental re-index on save. The CLI has no single-file
     * mode; scheduling a full (cache-aware) run avoids a process per save.
     */
    scheduleReindex(): void {
        if (this.reindexTimer) {
            clearTimeout(this.reindexTimer);
        }
        this.reindexTimer = setTimeout(() => {
            this.indexWorkspace()
                .then(() => this.outputChannel.appendLine('Auto re-index complete'))
                .catch(() => this.outputChannel.appendLine('Auto re-index failed'));
        }, 2000);
    }

    async search(query: string): Promise<SearchResult[]> {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceFolder) {
            return [];
        }

        return new Promise((resolve) => {
            this.spawnCli(['search', query, '--json'], workspaceFolder.uri.fsPath, (_code, stdout) => {
                try {
                    resolve(JSON.parse(stdout));
                } catch {
                    resolve([]);
                }
            });
        });
    }

    async getStatus(): Promise<StatusInfo> {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceFolder) {
            return { nodes: 0, edges: 0, files: 0 };
        }

        return new Promise((resolve) => {
            this.spawnCli(['status', '--json'], workspaceFolder.uri.fsPath, (_code, stdout) => {
                try {
                    resolve(JSON.parse(stdout));
                } catch {
                    resolve({ nodes: 0, edges: 0, files: 0 });
                }
            });
        });
    }

    async clearIndex(): Promise<void> {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceFolder) {
            return;
        }

        return new Promise((resolve) => {
            this.spawnCli(['clear'], workspaceFolder.uri.fsPath, () => resolve());
        });
    }
}
