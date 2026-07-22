# CodeNexus VS Code Extension

The context engine for AI coding agents - reduce tokens by 50-70%.

## Features

- **Context Search**: Search for relevant code across your workspace
- **CodeLens**: See usages and impact for functions and classes
- **Auto-indexing**: Automatically index files on save
- **Sidebar**: Quick access to status and search

## Installation

### From Source

1. Clone the repository
2. Navigate to `vscode-extension`
3. Run `npm install`
4. Run `npm run compile`
5. Press F5 to launch the extension

### From VSIX

1. Build the extension: `npm run package`
2. Install: `code --install-extension codenexus-0.1.0.vsix`

## Usage

### Commands

- `CodeNexus: Index Workspace` - Index all files in the workspace
- `CodeNexus: Search Context` - Search for code context
- `CodeNexus: Show Status` - Show index status
- `CodeNexus: Clear Index` - Clear the index

### CodeLens

Functions and classes will show:
- **Find Usages**: Search for all usages
- **Impact**: Show impact graph
- **Dependencies**: Show dependencies

### Sidebar

The sidebar provides:
- Index status (nodes, edges, files)
- Quick index button
- Search input
- Search results

## Requirements

- CodeNexus CLI installed (`pip install codenexus`)
- Python 3.10+

## Extension Settings

This extension contributes the following settings:

* `codenexus.enabled`: Enable/disable CodeNexus
* `codenexus.autoIndex`: Auto-index on file save
* `codenexus.maxTokens`: Maximum tokens for context capsule

## Known Issues

- None reported

## Release Notes

### 0.1.0

- Initial release
- Basic indexing and search
- CodeLens support
- Sidebar with status and search
