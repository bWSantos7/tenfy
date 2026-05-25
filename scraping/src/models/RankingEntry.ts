import mongoose, { Schema, Document } from 'mongoose';

export interface IRankingEntry extends Document {
    rankingId?: string;
    rankingDate?: string;
    updatedText?: string;
    category: string;
    rank: number;
    playerName: string;
    playerId?: string;
    profileId?: string;
    country?: string;
    dob?: string;
    singlesPoints?: string;
    doublesPoints?: string;
    bonusPoints?: string;
    totalPoints?: string;
    sourceUrl: string;
    lastUpdated: Date;
}

const RankingEntrySchema = new Schema<IRankingEntry>({
    rankingId: { type: String },
    rankingDate: { type: String },
    updatedText: { type: String },
    category: { type: String, required: true },
    rank: { type: Number, required: true },
    playerName: { type: String, required: true },
    playerId: { type: String },
    profileId: { type: String },
    country: { type: String },
    dob: { type: String },
    singlesPoints: { type: String },
    doublesPoints: { type: String },
    bonusPoints: { type: String },
    totalPoints: { type: String },
    sourceUrl: { type: String, required: true },
    lastUpdated: { type: Date, default: Date.now }
}, { timestamps: true });

RankingEntrySchema.index({ rankingId: 1, category: 1, playerId: 1 }, { unique: true, sparse: true });

export const RankingEntry = mongoose.model<IRankingEntry>('RankingEntry', RankingEntrySchema);
