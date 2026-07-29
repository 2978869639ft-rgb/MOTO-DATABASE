ALTER TABLE listing_observations ADD COLUMN condition_notes TEXT;
ALTER TABLE listing_observations ADD COLUMN registration_status TEXT;
ALTER TABLE listing_observations ADD COLUMN roadworthy_status TEXT;
ALTER TABLE listing_observations ADD COLUMN is_lams_approved INTEGER;
ALTER TABLE listing_observations ADD COLUMN is_modified INTEGER;
ALTER TABLE listing_observations ADD COLUMN listing_status TEXT DEFAULT 'unknown';
