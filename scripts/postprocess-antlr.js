#!/usr/bin/env node
/**
 * Post-processes ANTLR 4.13.2 TypeScript output for compatibility
 * with our CommonJS-based TypeScript project.
 *
 * Transforms:
 * 1. Strips .js extensions from relative imports
 * 2. Converts `export default class X` to `export class X` (named exports)
 * 3. Converts `import X from "./Y"` to `import { X } from "./Y"` for local files
 */

const fs = require('fs');
const path = require('path');

const generatedDir = path.join(__dirname, '..', 'src', 'parser', 'generated', 'grammar');

if (!fs.existsSync(generatedDir)) {
    console.error('Generated directory not found:', generatedDir);
    process.exit(1);
}

const tsFiles = fs.readdirSync(generatedDir).filter(f => f.endsWith('.ts'));
let totalChanges = 0;

for (const file of tsFiles) {
    const filePath = path.join(generatedDir, file);
    let content = fs.readFileSync(filePath, 'utf-8');
    let changes = 0;

    // 1. Strip .js extensions from relative imports
    const jsExtPattern = /from\s+["'](\.[^"']+)\.js["']/g;
    content = content.replace(jsExtPattern, (match, importPath) => {
        changes++;
        return `from "${importPath}"`;
    });

    // 2. Convert default exports to named exports
    content = content.replace(/^export default class /gm, (match) => {
        changes++;
        return 'export class ';
    });

    // 3. Convert default imports of local files to named imports
    // e.g., `import SysMLv2Visitor from "./SysMLv2Visitor"` → `import { SysMLv2Visitor } from "./SysMLv2Visitor"`
    const defaultImportPattern = /^import\s+(\w+)\s+from\s+["'](\.\/[^"']+)["']\s*;/gm;
    content = content.replace(defaultImportPattern, (match, name, importPath) => {
        changes++;
        return `import { ${name} } from "${importPath}";`;
    });

    // 4. In the Visitor file, remove all optional property declarations (visitXxx?:)
    // and add an index signature so accept() methods in the parser can reference
    // visitor methods dynamically.
    if (file.includes('Visitor')) {
        // Remove lines like: visitModel?: (ctx: ModelContext) => Result;
        const beforeLines = content.split('\n').length;
        content = content.replace(/^\s+visit\w+\?\s*:\s*\(ctx:.*?\)\s*=>\s*Result\s*;$/gm, '');
        // Also remove any jsdoc comments that precede now-removed lines
        content = content.replace(/\/\*\*\n(\s+\*[^\n]*\n)+\s+\*\/\n\s*$/gm, '');
        // Clean up multiple blank lines
        content = content.replace(/\n{3,}/g, '\n\n');

        // Add index signature to allow dynamic property access in accept() methods
        content = content.replace(
            /export class (\w+)<Result> extends ParseTreeVisitor<Result> \{/,
            'export class $1<Result> extends ParseTreeVisitor<Result> {\n' +
            '    [key: string]: any;'
        );

        const afterLines = content.split('\n').length;
        const removedLines = beforeLines - afterLines;
        if (removedLines > 0) {
            changes += removedLines;
            console.log(`    Removed ${removedLines} visitor property declarations`);
        }
    }

    if (changes > 0) {
        fs.writeFileSync(filePath, content, 'utf-8');
        console.log(`  ${file}: ${changes} changes`);
        totalChanges += changes;
    }
}

console.log(`Post-processed ${tsFiles.length} files, ${totalChanges} total changes`);
