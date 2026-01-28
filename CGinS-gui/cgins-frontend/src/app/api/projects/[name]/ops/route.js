import { NextResponse } from 'next/server';
import { jacSpawn } from '@/lib/jacBackend';

export async function GET(request, { params }) {
    const { name } = await params;
    if (!name) {
        return NextResponse.json({ error: 'Project name is required' }, { status: 400 });
    }

    try {
        const { reports } = await jacSpawn('list_ops', { project_name: name });
        return NextResponse.json({ ops: reports[0] || [] });
    } catch (error) {
        console.error('List ops error:', error);
        return NextResponse.json({ error: 'Failed to list ops' }, { status: 500 });
    }
}
