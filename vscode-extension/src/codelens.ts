import * as vscode from 'vscode';
import { CodeNexusService } from './service';

export class CodeNexusCodeLensProvider implements vscode.CodeLensProvider {
    private _onDidChangeCodeLenses = new vscode.EventEmitter<void>();
    public readonly onDidChangeCodeLenses = this._onDidChangeCodeLenses.event;

    constructor(private readonly _service: CodeNexusService) {}

    provideCodeLenses(document: vscode.TextDocument): vscode.CodeLens[] {
        const lenses: vscode.CodeLens[] = [];
        const text = document.getText();

        // Find function and class definitions
        const functionRegex = /^(?:export\s+)?(?:async\s+)?(?:function|def|fn|func)\s+(\w+)/gm;
        const classRegex = /^(?:export\s+)?(?:class|struct|interface|type)\s+(\w+)/gm;

        let match;

        // Function lenses
        while ((match = functionRegex.exec(text))) {
            const line = document.lineAt(document.positionAt(match.index));
            const range = new vscode.Range(line.range.start, line.range.end);

            lenses.push(new vscode.CodeLens(range, {
                title: "$(search) Find Usages",
                command: "codenexus.search",
                arguments: [match[1]]
            }));

            lenses.push(new vscode.CodeLens(range, {
                title: "$(graph) Impact",
                command: "codenexus.search",
                arguments: [`impact:${match[1]}`]
            }));
        }

        // Class lenses
        while ((match = classRegex.exec(text))) {
            const line = document.lineAt(document.positionAt(match.index));
            const range = new vscode.Range(line.range.start, line.range.end);

            lenses.push(new vscode.CodeLens(range, {
                title: "$(search) Find Usages",
                command: "codenexus.search",
                arguments: [match[1]]
            }));

            lenses.push(new vscode.CodeLens(range, {
                title: "$(graph) Impact",
                command: "codenexus.search",
                arguments: [`impact:${match[1]}`]
            }));

            lenses.push(new vscode.CodeLens(range, {
                title: "$(info) Dependencies",
                command: "codenexus.search",
                arguments: [`deps:${match[1]}`]
            }));
        }

        return lenses;
    }
}
