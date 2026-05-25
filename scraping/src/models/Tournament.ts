import mongoose, { Schema, Document } from 'mongoose';

export interface ITournamentEvent {
    eventId?: string;
    name: string;
    draws?: number;
    entries?: number;
}

export interface ITournament extends Document {
    cosatId: string;
    name: string;
    url: string;
    organization?: string;
    location?: string;
    city?: string;
    state?: string;
    country?: string;
    modality?: string;
    dateRange?: string;
    registration_open_at?: string;
    registration_close_at?: string;
    withdrawal_deadline_at?: string;
    tournament_start_at?: string;
    tournament_end_at?: string;
    timezone?: string;
    source_dates_raw?: any;
    hasOnlineEntry?: boolean;
    categoriesCount?: number;
    entriesCount?: number;
    playersCount?: number;
    events: ITournamentEvent[];
    sync_status?: string;
    validation_errors?: string[];
    normalized_at?: Date;
    lastUpdated: Date;
}

const VALID_UF = new Set([
    'AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS',
    'MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC',
    'SP','SE','TO'
]);

const TournamentEventSchema = new Schema<ITournamentEvent>({
    eventId: { type: String },
    name: { type: String, required: true },
    draws: { type: Number },
    entries: { type: Number }
}, { _id: false });

const TournamentSchema = new Schema<ITournament>({
    cosatId: { type: String, required: true, unique: true },
    name: { type: String, required: true },
    url: { type: String, required: true },
    organization: { type: String },
    location: { type: String },
    city: { type: String },
    state: { type: String, maxlength: 2 },
    country: { type: String },
    modality: { type: String, default: 'tennis' },
    dateRange: { type: String },
    registration_open_at: { type: String },
    registration_close_at: { type: String },
    withdrawal_deadline_at: { type: String },
    tournament_start_at: { type: String },
    tournament_end_at: { type: String },
    timezone: { type: String },
    source_dates_raw: { type: Object },
    hasOnlineEntry: { type: Boolean, default: false },
    categoriesCount: { type: Number },
    entriesCount: { type: Number },
    playersCount: { type: Number },
    events: { type: [TournamentEventSchema], default: [] },
    sync_status: { type: String, enum: ['pending', 'synced', 'error'], default: 'pending' },
    validation_errors: { type: [String], default: [] },
    normalized_at: { type: Date },
    lastUpdated: { type: Date, default: Date.now }
}, { timestamps: true });

export { VALID_UF };

export const Tournament = mongoose.model<ITournament>('Tournament', TournamentSchema);
