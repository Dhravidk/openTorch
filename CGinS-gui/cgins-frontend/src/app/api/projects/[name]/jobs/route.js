import { NextResponse } from 'next/server';
import { jacSpawn } from '@/lib/jacBackend';

export async function POST(request, { params }) {
    const { name } = await params;
    if (!name) {
        return NextResponse.json({ error: 'Project name is required' }, { status: 400 });
    }

    try {
        const body = await request.json();
        const jobType = body?.job_type;
        if (!jobType) {
            return NextResponse.json({ error: 'job_type is required' }, { status: 400 });
        }

        const { reports } = await jacSpawn('start_job', {
            project_name: name,
            job_type: jobType,
        });
        const out = reports[0] || {};
        if (out.error) {
            return NextResponse.json({ error: out.error }, { status: 400 });
        }
        return NextResponse.json({ job: out });
    } catch (error) {
        console.error('Start job error:', error);
        return NextResponse.json({ error: 'Failed to start job' }, { status: 500 });
    }
}
