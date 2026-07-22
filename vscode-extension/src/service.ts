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

    constructor() {
        this.outputChannel = vscode.window.createOutputChannel('CodeNexus');
    }

    isSupportedFile(fileName: string): boolean {
        const extensions = ['.py', '.js', '.jsx', '.ts', '.tsx', '.go', '.rs', '.java', '.cs'];
        return extensions.some(ext => fileName.endsWith(ext));
    }

    async indexWorkspace(): Promise<void> {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceFolder) {
            vscode.window.showErrorMessage('No workspace folder found');
            return;
        }

        return new Promise((resolve, reject) => {
            const process = spawn('codenexus', ['index'], {
                cwd: workspaceFolder.uri.fsPath,
                shell: true
            });

            let output = '';
            process.stdout?.on('data', (data) => {
                output += data.toString();
            });

            process.stderr?.on('data', (data) => {
                output += data.toString();
            });

            process.on('close', (code) => {
                this.outputChannel.appendLine(output);
                if (code === 0) {
                    resolve();
                } else {
                    reject(new Error(`Indexing failed with code ${code}`));
                }
            });
        });
    }

    async indexFile(filePath: string): Promise<void> {
        // Simplified file indexing
        this.outputChannel.appendLine(`Indexing file: ${filePath}`);
    }

    async search(query: string): Promise<SearchResult[]> {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceFolder) {
            return [];
        }

        return new Promise((resolve) => {
            const process = spawn('codenexus', ['search', query, '--json'], {
                cwd: workspaceFolder.uri.fsPath,
                shell: true
            });

            let output = '';
            process.stdout?.on('data', (data) => {
                output += data.toString();
            });

            process.on('close', () => {
                try {
                    const results = JSON.parse(output);
                    resolve(results);
                } catch {
                    resolve([]);
                }
            });

            process.on('error', () => {
                resolve([]);
            });
        });
    }

    async getStatus(): Promise<StatusInfo> {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceFolder) {
            return { nodes: 0, edges: 0, files: 0 };
        }

        return new Promise((resolve) => {
            const process = spawn('codenexus', ['status', '--json'], {
                cwd: workspaceFolder.uri.fsPath,
                shell: true
            });

            let output = '';
            process.stdout?.on('data', (data) => {
                output += data.toString();
            });

            process.on('close', () => {
                try {
                    const status = JSON.parse(output);
                    resolve(status);
                } catch {
                    resolve({ nodes: 0, edges: 0, files: 0 });
                }
            });

            process.on('error', () => {
                resolve({ nodes: 0, edges: 0, files: 0 });
            });
        });
    }

    async clearIndex(): Promise<void> {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceFolder) {
            return;
        }

        return new Promise((resolve) => {
            const process = spawn('codenexus', ['clear'], {
                cwd: workspaceFolder.uri.fsPath,
                shell: true
            });

            process.on('close', () => {
                resolve();
            });

            process.on('error', () => {
                resolve();
            });
        });
    }
}
