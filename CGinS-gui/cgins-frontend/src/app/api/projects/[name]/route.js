import { NextResponse } from 'next/server';
import { jacSpawn } from '@/lib/jacBackend';

export async function GET(request, { params }) {
    const { name } = await params;

    if (!name) {
        return NextResponse.json({ error: 'Project name is required' }, { status: 400 });
    }

    try {
        const { reports } = await jacSpawn('get_project', { name });
        const out = reports[0] || {};
        if (out.error) {
            return NextResponse.json({ error: out.error }, { status: 404 });
        }
        return NextResponse.json({ project: out });
    } catch (error) {
        console.error('Get project error:', error);
        return NextResponse.json({ error: 'Failed to get project' }, { status: 500 });
    }
}

export async function DELETE(request, { params }) {
    const { name } = await params;

    if (!name) {
        return NextResponse.json({ error: 'Project name is required' }, { status: 400 });
    }

    try {
        const { reports } = await jacSpawn('delete_project', { name });
        const out = reports[0] || {};
        if (out.error) {
            return NextResponse.json({ error: out.error }, { status: 404 });
        }
        return NextResponse.json({ success: true, message: `Project ${name} deleted` });
    } catch (error) {
        console.error('Delete project error:', error);
        return NextResponse.json({ error: 'Failed to delete project' }, { status: 500 });
    }
}

export async function PATCH(request, { params }) {
    const { name } = await params;
    if (!name) {
        return NextResponse.json({ error: 'Project name is required' }, { status: 400 });
    }

    try {
        const { reports } = await jacSpawn('get_project', { name });
        const out = reports[0] || {};
        if (out.error) {
            return NextResponse.json({ error: out.error }, { status: 404 });
        }
        return NextResponse.json({ success: true, last_accessed: out.last_accessed_at || null });
    } catch (error) {
        console.error('Update project accessed time error:', error);
        return NextResponse.json({ error: 'Failed to update project' }, { status: 500 });
    }
}
