import mongoose, { Schema, Document } from 'mongoose';

export interface IAthlete extends Document {
    name: string;
    rankingCategory?: string;
    points?: string;
    cosatId?: string; // Para evitar duplicatas
    lastUpdated: Date;
}

const AthleteSchema: Schema = new Schema({
    name: { type: String, required: true },
    rankingCategory: { type: String },
    points: { type: String },
    cosatId: { type: String, unique: true, sparse: true },
    lastUpdated: { type: Date, default: Date.now }
}, { timestamps: true });

export const Athlete = mongoose.model<IAthlete>('Athlete', AthleteSchema);