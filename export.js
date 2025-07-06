const fs = require("fs");
const path = require("path");

const allowedExtensions = [".js", ".json", ".html", ".css", ".md", ".py"];
const ignoredDirs = ["node_modules", "venv", "__pycache__", ".git"];
const ignoredFiles = [
  "exportProject.js",
  "client_secret.json",
  "token.json",
  "gitignore",
  "content_library.json",
];

function shouldIgnore(filePath) {
  return ignoredDirs.some((dir) =>
    filePath.includes(path.sep + dir + path.sep)
  );
}

function gatherFiles(dir, collected = []) {
  const entries = fs.readdirSync(dir);
  for (const entry of entries) {
    const fullPath = path.join(dir, entry);
    const stats = fs.statSync(fullPath);
    if (stats.isDirectory()) {
      if (!ignoredDirs.includes(entry)) {
        gatherFiles(fullPath, collected);
      }
    } else if (
      allowedExtensions.includes(path.extname(entry)) &&
      !shouldIgnore(fullPath) &&
      !ignoredFiles.includes(entry)
    ) {
      collected.push(fullPath);
    }
  }
  return collected;
}

function exportFiles() {
  const files = gatherFiles(".");
  const output = [];

  for (const file of files) {
    const content = fs.readFileSync(file, "utf8");
    output.push(`--- ${file} ---\n${content}`);
  }

  fs.writeFileSync("project_export.txt", output.join("\n\n"));
  console.log(
    `✅ Export complete! ${files.length} files written to project_export.txt`
  );
}

exportFiles();
