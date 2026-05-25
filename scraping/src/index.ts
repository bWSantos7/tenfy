import cron from 'node-cron';
import { connectDB } from './config/database';
import { startScraping } from './services/scraper';

const timezone = process.env.TZ || 'America/Sao_Paulo';
const isScraperEnabled = process.env.SCRAPER_ENABLED === 'true';
const shouldRunOnStart = process.env.RUN_ON_START === 'true';
let isJobRunning = false;

async function runScrapingJob(trigger: string) {
    if (!isScraperEnabled) {
        console.log('Scraper desativado. Defina SCRAPER_ENABLED=true somente se houver autorizacao para coletar esses dados.');
        return;
    }

    if (isJobRunning) {
        console.log(`[${new Date().toLocaleString('pt-BR')}] Job ignorado (${trigger}): uma extracao ainda esta em andamento.`);
        return;
    }

    isJobRunning = true;

    try {
        console.log(`[${new Date().toLocaleString('pt-BR')}] Iniciando extracao COSAT (${trigger})...`);
        await Promise.race([
            startScraping(),
            new Promise((_, reject) =>
                setTimeout(() => reject(new Error('Job timeout: 8 minutos excedidos')), 8 * 60 * 1000)
            ),
        ]);
        console.log(`[${new Date().toLocaleString('pt-BR')}] Extracao COSAT finalizada.`);
    } catch (error) {
        console.error(`[${new Date().toLocaleString('pt-BR')}] Falha no job COSAT:`, error);
    } finally {
        isJobRunning = false;
    }
}

const run = async () => {
    await connectDB();

    console.log(`Scheduler iniciado. Timezone: ${timezone}. Frequencia: diariamente as 3h.`);

    if (shouldRunOnStart) {
        await runScrapingJob('startup');
    }

    cron.schedule('0 3 * * *', async () => {
        await runScrapingJob('cron');
    }, { timezone });
};

run().catch(error => {
    console.error('Falha ao iniciar o scheduler:', error);
    process.exit(1);
});
