import { NextResponse } from 'next/server';
import { promises as fs } from 'fs';
import path from 'path';
import { jacSpawn } from '@/lib/jacBackend';

const REPO_ROOT = path.resolve(process.cwd(), '..');
const UPLOADS_DIR = path.join(REPO_ROOT, 'projects', '_uploads');

async function saveUpload(file, targetPath) {
    if (!file || !file.arrayBuffer) return null;
    const buffer = Buffer.from(await file.arrayBuffer());
    await fs.mkdir(path.dirname(targetPath), { recursive: true });
    await fs.writeFile(targetPath, buffer);
    return targetPath;
}

export async function POST(request) {
    try {
        const formData = await request.formData();
        const projectName = formData.get('projectName');
        const code = formData.get('code');
        const mode = (formData.get('mode') || 'A').toString();
        const weightsFile = formData.get('weightsFile'); // File object
        const fullModelFile = formData.get('fullModelFile');
        const exampleInputsFile = formData.get('exampleInputsFile');

        if (!projectName) {
            return NextResponse.json({ error: 'Project name is required' }, { status: 400 });
        }

        if (!exampleInputsFile || !exampleInputsFile.size) {
            return NextResponse.json(
                { error: 'example_inputs.pt is required' },
                { status: 400 }
            );
        }
        if (mode === 'B' && (!fullModelFile || !fullModelFile.size)) {
            return NextResponse.json(
                { error: 'full_model.pt is required for Mode B' },
                { status: 400 }
            );
        }

        const uploadDir = path.join(UPLOADS_DIR, projectName);
        const weightsPath = weightsFile && weightsFile.size > 0
            ? path.join(uploadDir, 'weights.pt')
            : '';
        const fullModelPath = fullModelFile && fullModelFile.size > 0
            ? path.join(uploadDir, 'full_model.pt')
            : '';
        const exampleInputsPath = path.join(uploadDir, 'example_inputs.pt');

        if (weightsFile && weightsFile.size > 0) {
            await saveUpload(weightsFile, weightsPath);
        }
        if (fullModelFile && fullModelFile.size > 0) {
            await saveUpload(fullModelFile, fullModelPath);
        }
        await saveUpload(exampleInputsFile, exampleInputsPath);

        const { reports } = await jacSpawn('create_project', {
            name: projectName,
            mode,
            model_code: code || '',
            weights_path: weightsPath || '',
            example_inputs_path: exampleInputsPath,
            full_model_path: fullModelPath || '',
        });

        const out = reports[0] || {};
        if (out.error) {
            const status = out.error.toLowerCase().includes("already exists") ? 409 : 400;
            return NextResponse.json({ error: out.error }, { status });
        }

        return NextResponse.json({ success: true, name: projectName });

    } catch (error) {
        console.error('Project creation error:', error);
        return NextResponse.json({ error: 'Failed to create project' }, { status: 500 });
    }
}

export async function GET() {
    try {
        const { reports } = await jacSpawn('list_projects');
        const list = reports[0] || [];
        const projects = list.map((p) => {
            const last = p.last_accessed_at || p.created_at || null;
            const lastModified = typeof last === 'number'
                ? new Date(last * 1000).toISOString()
                : last;
            return {
                name: p.name,
                lastModified: lastModified || new Date(0).toISOString(),
            };
        });

        projects.sort((a, b) => new Date(b.lastModified) - new Date(a.lastModified));
        return NextResponse.json({ projects });
    } catch (error) {
        console.error('List projects error:', error);
        return NextResponse.json({ error: 'Failed to list projects' }, { status: 500 });
    }
}
