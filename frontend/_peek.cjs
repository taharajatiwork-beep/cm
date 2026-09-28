const fs = require("fs");
const lines = fs.readFileSync("src/api.ts", "utf8").split("\n");
for (const i of [139, 140, 141, 451, 452, 453, 454]) {
  console.log(i + 1, JSON.stringify(lines[i]));
}
