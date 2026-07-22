import * as vscode from 'vscode';
import { CodeNexusSidebarProvider } from './sidebar';
import { CodeNexusCodeLensProvider } from './codelens';
import { CodeNexusService } from './service';

let service: CodeNexusService;

export function activate(context: vscode.ExtensionContext) {
    console.log('CodeNexus extension is now active');

    // Initialize service
    service = new CodeNexusService();

    // Register sidebar provider
    const sidebarProvider = new CodeNexusSidebarProvider(context.extensionUri, service);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider('codenexus.sidebar', sidebarProvider)
    );

    // Register CodeLens provider
    const codeLensProvider = new CodeNexusCodeLensProvider(service);
    context.subscriptions.push(
        vscode.languages.registerCodeLensProvider('*', codeLensProvider)
    );

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('codenexus.index', async () => {
            await service.indexWorkspace();
            vscode.window.showInformationMessage('CodeNexus: Workspace indexed');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('codenexus.search', async () => {
            const query = await vscode.window.showInputBox({
                prompt: 'Enter search query',
                placeHolder: 'e.g., authentication middleware'
            });

            if (query) {
                const results = await service.search(query);
                // Show results in a quick pick
                const items = results.map(r => ({
                    label: r.name,
                    description: r.file,
                    detail: `${r.type} - Score: ${r.score.toFixed(4)}`
                }));

                const selected = await vscode.window.showQuickPick(items, {
                    placeHolder: 'Select a result'
                });

                if (selected) {
                    // Open the file
                    const uri = vscode.Uri.file(selected.description);
                    const document = await vscode.workspace.openTextDocument(uri);
                    await vscode.window.showTextDocument(document);
                }
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('codenexus.status', async () => {
            const status = await service.getStatus();
            vscode.window.showInformationMessage(
                `CodeNexus: ${status.nodes} nodes, ${status.edges} edges, ${status.files} files`
            );
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('codenexus.clear', async () => {
            await service.clearIndex();
            vscode.window.showInformationMessage('CodeNexus: Index cleared');
        })
    );

    // Auto-index on file save
    if (vscode.workspace.getConfiguration('codenexus').get('autoIndex')) {
        context.subscriptions.push(
            vscode.workspace.onDidSaveTextDocument(async (document) => {
                if (service.isSupportedFile(document.fileName)) {
                    await service.indexFile(document.fileName);
                }
            })
        );
    }
}

export function deactivate() {
    console.log('CodeNexus extension is now deactivated');
}
