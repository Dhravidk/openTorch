import { NextResponse } from 'next/server';
import { jacSpawn } from '@/lib/jacBackend';

const defaultConfig = {
    llm_info: {
        model: '',
        apikey: '',
        provider: 'anthropic',
    },
};

export async function GET() {
    try {
        const { reports } = await jacSpawn('get_config');
        const cfg = reports[0] || {};
        const provider = cfg.llm_provider || 'anthropic';
        let apikey = '';
        if (provider === 'openai') {
            apikey = cfg.openai_api_key || '';
        } else if (provider === 'gemini') {
            apikey = cfg.google_api_key || '';
        } else {
            apikey = cfg.anthropic_api_key || '';
        }

        return NextResponse.json({
            llm_info: {
                model: cfg.llm_model || '',
                apikey,
                provider,
            },
        });
    } catch (error) {
        return NextResponse.json(defaultConfig);
    }
}

export async function POST(request) {
    try {
        const body = await request.json();
        const llmInfo = body?.llm_info || {};
        const provider = llmInfo.provider || 'anthropic';
        const model = llmInfo.model || '';
        const apikey = llmInfo.apikey || '';

        const { reports } = await jacSpawn('get_config');
        const current = reports[0] || {};

        const payload = {
            llm_provider: provider,
            llm_model: model,
            openai_api_key: current.openai_api_key || '',
            anthropic_api_key: current.anthropic_api_key || '',
            google_api_key: current.google_api_key || '',
        };

        if (provider === 'openai') {
            payload.openai_api_key = apikey;
        } else if (provider === 'gemini') {
            payload.google_api_key = apikey;
        } else {
            payload.anthropic_api_key = apikey;
        }

        await jacSpawn('save_config', payload);
        return NextResponse.json({ success: true, config: body });
    } catch (error) {
        return NextResponse.json({ error: 'Failed to save config' }, { status: 500 });
    }
}
