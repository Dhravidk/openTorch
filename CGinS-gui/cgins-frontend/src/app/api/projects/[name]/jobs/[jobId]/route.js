import { NextResponse } from 'next/server';
import { jacSpawn } from '@/lib/jacBackend';

export async function GET(request, { params }) {
    const { name, jobId } = await params;
    if (!name || !jobId) {
        return NextResponse.json({ error: 'project name and jobId are required' }, { status: 400 });
    }

    try {
        const { reports } = await jacSpawn('get_job', {
            project_name: name,
            job_id: jobId,
            tail_lines: 400,
        });
        const out = reports[0] || {};
        if (out.error) {
            return NextResponse.json({ error: out.error }, { status: 404 });
        }
        return NextResponse.json({ job: out });
    } catch (error) {
        console.error('Get job error:', error);
        return NextResponse.json({ error: 'Failed to get job' }, { status: 500 });
    }
}
