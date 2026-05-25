import mongoose, { Schema, Document } from 'mongoose';

export interface IPlayer extends Document {
    name: string;
    country?: string;
    countryCode?: string;
    tournamentId?: string;
    tournamentName?: string;
    tournamentPlayerId?: string;
    rankingPlayerId?: string;
    profileId?: string;
    dob?: string;
    rankingCategory?: string;
    lastUpdated: Date;
}

const PlayerSchema = new Schema<IPlayer>({
    name: { type: String, required: true },
    country: { type: String },
    countryCode: { type: String },
    tournamentId: { type: String },
    tournamentName: { type: String },
    tournamentPlayerId: { type: String },
    rankingPlayerId: { type: String },
    profileId: { type: String },
    dob: { type: String },
    rankingCategory: { type: String },
    lastUpdated: { type: Date, default: Date.now }
}, { timestamps: true });

PlayerSchema.index({ tournamentId: 1, tournamentPlayerId: 1 }, { unique: true, sparse: true });
PlayerSchema.index({ profileId: 1 }, { sparse: true });
PlayerSchema.index({ rankingPlayerId: 1, rankingCategory: 1 }, { sparse: true });

export const Player = mongoose.model<IPlayer>('Player', PlayerSchema);
