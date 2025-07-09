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
    temperature_celsius FLOAT,
    weather_condition VARCHAR(100),
    humidity_percent INTEGER,
    wind_speed_kmh FLOAT,
    precipitation_mm FLOAT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(location, date)
);

-- Create calendar_insights table
CREATE TABLE IF NOT EXISTS calendar_insights (
    id SERIAL PRIMARY KEY,
    location VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    opportunity_score INTEGER NOT NULL CHECK (opportunity_score >= 0 AND opportunity_score <= 100),
    event_count INTEGER DEFAULT 0,
    weather_score INTEGER DEFAULT 0,
    seasonal_score INTEGER DEFAULT 0,
    insights JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(location, date)
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_events_location ON events(location);
CREATE INDEX IF NOT EXISTS idx_events_start_time ON events(start_time);
CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);
CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);

CREATE INDEX IF NOT EXISTS idx_weather_location_date ON weather_data(location, date);
CREATE INDEX IF NOT EXISTS idx_calendar_insights_location_date ON calendar_insights(location, date);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger to auto-update updated_at for events
CREATE TRIGGER update_events_updated_at 
    BEFORE UPDATE ON events 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Insert sample data for testing
INSERT INTO events (event_id, name, description, location, start_time, end_time, category, attendance_estimate, source, url) VALUES
('test-event-1', 'Sample Tech Conference', 'A sample technology conference for testing', 'San Francisco, CA', '2025-01-15 10:00:00+00', '2025-01-15 18:00:00+00', 'technology', 500, 'test', 'https://example.com/event1'),
('test-event-2', 'Sample Music Festival', 'A sample music festival for testing', 'Los Angeles, CA', '2025-01-20 12:00:00+00', '2025-01-20 23:00:00+00', 'music', 5000, 'test', 'https://example.com/event2')
ON CONFLICT (event_id) DO NOTHING;

INSERT INTO weather_data (location, date, temperature_celsius, weather_condition, humidity_percent, wind_speed_kmh, precipitation_mm) VALUES
('San Francisco, CA', '2025-01-15', 18.5, 'partly_cloudy', 65, 12.0, 0.0),
('Los Angeles, CA', '2025-01-20', 22.0, 'sunny', 45, 8.5, 0.0)
ON CONFLICT (location, date) DO NOTHING;

INSERT INTO calendar_insights (location, date, opportunity_score, event_count, weather_score, seasonal_score, insights) VALUES
('San Francisco, CA', '2025-01-15', 75, 1, 80, 70, '{"recommendation": "Good day for outdoor events", "weather_factor": "mild temperature", "event_density": "moderate"}'),
('Los Angeles, CA', '2025-01-20', 85, 1, 90, 80, '{"recommendation": "Excellent day for events", "weather_factor": "perfect sunny weather", "event_density": "moderate"}')
ON CONFLICT (location, date) DO NOTHING;

-- Grant permissions to dora user
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO dora;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO dora;