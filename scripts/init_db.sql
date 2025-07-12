-- Initialize Dora database schema
-- PostgreSQL database initialization script

-- Create database if not exists (handled by POSTGRES_DB env var)

-- Create events table
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(500) NOT NULL,
    description TEXT,
    location VARCHAR(500),
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE NOT NULL,
    category VARCHAR(100) DEFAULT 'general',
    attendance_estimate INTEGER DEFAULT 0,
    source VARCHAR(100) NOT NULL,
    url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create weather_data table
CREATE TABLE IF NOT EXISTS weather_data (
    id SERIAL PRIMARY KEY,
    location VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    temperature FLOAT,
    weather_condition VARCHAR(100),
    humidity FLOAT,
    wind_speed FLOAT,
    precipitation FLOAT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(location, date)
);

-- Create calendar_insights table
CREATE TABLE IF NOT EXISTS calendar_insights (
    id SERIAL PRIMARY KEY,
    location VARCHAR(255) NOT NULL,
    insight_date DATE NOT NULL,
    insights JSONB NOT NULL,
    opportunity_score FLOAT CHECK (opportunity_score >= 0.0 AND opportunity_score <= 1.0),
    marketing_recommendations TEXT[],
    conflict_warnings TEXT[],
    weather_impact VARCHAR(100),
    event_density VARCHAR(50),
    peak_hours TEXT[],
    generated_by VARCHAR(100),
    confidence_score FLOAT CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(location, insight_date)
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_events_location ON events(location);
CREATE INDEX IF NOT EXISTS idx_events_start_time ON events(start_time);
CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);
CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);

CREATE INDEX IF NOT EXISTS idx_weather_location_date ON weather_data(location, date);
CREATE INDEX IF NOT EXISTS idx_calendar_insights_location_date ON calendar_insights(location, insight_date);
CREATE INDEX IF NOT EXISTS idx_calendar_insights_opportunity_score ON calendar_insights(opportunity_score);
CREATE INDEX IF NOT EXISTS idx_calendar_insights_generated_by ON calendar_insights(generated_by);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers to auto-update updated_at columns
CREATE TRIGGER update_events_updated_at 
    BEFORE UPDATE ON events 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_weather_data_updated_at 
    BEFORE UPDATE ON weather_data 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_calendar_insights_updated_at 
    BEFORE UPDATE ON calendar_insights 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Insert sample data for testing
INSERT INTO events (event_id, name, description, location, start_time, end_time, category, attendance_estimate, source, url) VALUES
('test-event-1', 'Sample Tech Conference', 'A sample technology conference for testing', 'San Francisco, CA', '2025-01-15 10:00:00+00', '2025-01-15 18:00:00+00', 'technology', 500, 'test', 'https://example.com/event1'),
('test-event-2', 'Sample Music Festival', 'A sample music festival for testing', 'Los Angeles, CA', '2025-01-20 12:00:00+00', '2025-01-20 23:00:00+00', 'music', 5000, 'test', 'https://example.com/event2')
ON CONFLICT (event_id) DO NOTHING;

INSERT INTO weather_data (location, date, temperature, weather_condition, humidity, wind_speed, precipitation) VALUES
('San Francisco, CA', '2025-01-15', 18.5, 'partly_cloudy', 65.0, 12.0, 0.0),
('Los Angeles, CA', '2025-01-20', 22.0, 'sunny', 45.0, 8.5, 0.0)
ON CONFLICT (location, date) DO NOTHING;

INSERT INTO calendar_insights (location, insight_date, insights, opportunity_score, marketing_recommendations, conflict_warnings, weather_impact, event_density, peak_hours, generated_by, confidence_score) VALUES
('San Francisco, CA', '2025-01-15', '{"recommendation": "Good day for outdoor events", "weather_factor": "mild temperature", "event_density": "moderate"}', 0.75, ARRAY['Consider outdoor venue setup', 'Market to tech professionals'], ARRAY[], 'positive', 'medium', ARRAY['10:00', '14:00'], 'calendar_intelligence_agent', 0.85),
('Los Angeles, CA', '2025-01-20', '{"recommendation": "Excellent day for events", "weather_factor": "perfect sunny weather", "event_density": "moderate"}', 0.85, ARRAY['Perfect for outdoor events', 'High attendance expected', 'Premium pricing opportunity'], ARRAY[], 'positive', 'medium', ARRAY['12:00', '15:00', '18:00'], 'calendar_intelligence_agent', 0.92)
ON CONFLICT (location, insight_date) DO NOTHING;

-- Grant permissions to dora user
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO dora;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO dora;