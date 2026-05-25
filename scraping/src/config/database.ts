import mongoose from 'mongoose';
import dotenv from 'dotenv';

dotenv.config();

export const connectDB = async () => {
    try {
        const mongoUrl = process.env.DATABASE_URL;
        if (!mongoUrl) {
            throw new Error("A variável DATABASE_URL não foi definida.");
        }

        await mongoose.connect(mongoUrl);
        console.log('📦 Conectado ao MongoDB com sucesso.');
    } catch (error) {
        console.error('❌ Erro ao conectar ao MongoDB:', error);
        process.exit(1);
    }
};