import { NextResponse } from "next/server";
import fs from "fs/promises";
import path from "path";

export async function GET(request, { params }) {
  const { name } = await params;
  if (!name) {
    return NextResponse.json({ error: "Project name is required" }, { status: 400 });
  }

  const repoRoot = path.resolve(process.cwd(), "..");
  const benchmarkPath = path.join(repoRoot, "projects", name, "benchmark.json");

  try {
    const raw = await fs.readFile(benchmarkPath, "utf-8");
    const parsed = JSON.parse(raw);
    return NextResponse.json({ benchmark: parsed });
  } catch (error) {
    if (error && error.code === "ENOENT") {
      return NextResponse.json({ benchmark: null }, { status: 404 });
    }
    console.error("Benchmark read error:", error);
    return NextResponse.json({ error: "Failed to read benchmark" }, { status: 500 });
  }
}
