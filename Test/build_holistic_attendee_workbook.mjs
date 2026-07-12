import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [inputJson, outputXlsx, renderDir] = process.argv.slice(2);
const rows = JSON.parse(await fs.readFile(inputJson, "utf8"));
const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Attendee_Counts");
sheet.showGridLines = false;
sheet.getRange(`A1:B${rows.length + 1}`).values = [
  ["Transaction_ID", "Attendee_Count"],
  ...rows.map((item) => [String(item.Transaction_ID), Number(item.Attendee_Count)]),
];
sheet.getRange("A1:B1").format = {
  fill: "#1F4E78", font: { bold: true, color: "#FFFFFF" },
  borders: { preset: "outside", style: "thin", color: "#1F4E78" },
};
sheet.getRange(`A2:B${rows.length + 1}`).format.borders = { preset: "inside", style: "thin", color: "#D9E2F3" };
sheet.getRange(`B2:B${rows.length + 1}`).format.numberFormat = "0";
sheet.getRange("A:A").format.columnWidth = 24;
sheet.getRange("B:B").format.columnWidth = 18;
sheet.freezePanes.freezeRows(1);
const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputXlsx);
await fs.mkdir(renderDir, { recursive: true });
const preview = await workbook.render({ sheetName: "Attendee_Counts", autoCrop: "all", scale: 2, format: "png" });
await fs.writeFile(`${renderDir}/Attendee_Counts.png`, new Uint8Array(await preview.arrayBuffer()));
const inspect = await workbook.inspect({ kind: "table", range: `Attendee_Counts!A1:B${rows.length + 1}`, include: "values,formulas", tableMaxRows: 30, tableMaxCols: 4 });
await fs.writeFile(`${renderDir}/inspect.ndjson`, inspect.ndjson, "utf8");
