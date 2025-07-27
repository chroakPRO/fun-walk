'use client';

import { useState, useEffect, useRef } from 'react';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { MapPin, Search, Loader2 } from 'lucide-react';
import { Coordinate } from '@/types/route';

interface AddressInputProps {
  onLocationSelect: (coordinate: Coordinate) => void;
  placeholder?: string;
  label?: string;
}

interface SearchResult extends Coordinate {
  display_name: string;
  place_id: string;
  importance: number;
}

export default function AddressInput({ onLocationSelect, placeholder = "Enter address or place name", label }: AddressInputProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Debounced search function
  const searchAddresses = async (searchQuery: string) => {
    if (searchQuery.length < 3) {
      setResults([]);
      setShowResults(false);
      return;
    }

    setLoading(true);
    try {
      const response = await fetch('/api/search-addresses', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: searchQuery,
          limit: 5
        }),
      });

      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          setResults(data.results);
          setShowResults(data.results.length > 0);
        }
      }
    } catch (error) {
      console.error('Address search error:', error);
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  // Handle input change with debouncing
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newQuery = e.target.value;
    setQuery(newQuery);
    setSelectedIndex(-1);

    // Clear previous timeout
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }

    // Set new timeout for debounced search
    timeoutRef.current = setTimeout(() => {
      searchAddresses(newQuery);
    }, 300);
  };

  const handleResultSelect = (result: SearchResult) => {
    onLocationSelect({ lat: result.lat, lng: result.lng });
    setQuery(result.display_name);
    setShowResults(false);
    setSelectedIndex(-1);
  };

  // Handle keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!showResults || results.length === 0) return;

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex(prev => 
          prev < results.length - 1 ? prev + 1 : prev
        );
        break;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex(prev => prev > 0 ? prev - 1 : -1);
        break;
      case 'Enter':
        e.preventDefault();
        if (selectedIndex >= 0 && selectedIndex < results.length) {
          handleResultSelect(results[selectedIndex]);
        }
        break;
      case 'Escape':
        setShowResults(false);
        setSelectedIndex(-1);
        break;
    }
  };

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setShowResults(false);
        setSelectedIndex(-1);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  return (
    <div ref={containerRef} className="space-y-2 relative">
      {label && <label className="text-sm font-medium">{label}</label>}
      <div className="relative">
        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
          {loading ? (
            <Loader2 className="h-4 w-4 text-muted-foreground animate-spin" />
          ) : (
            <Search className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
        
        <Input
          value={query}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (results.length > 0) {
              setShowResults(true);
            }
          }}
          placeholder={placeholder}
          className="pl-10"
        />
      </div>

      {showResults && results.length > 0 && (
        <Card className="absolute top-full left-0 right-0 z-50 mt-1">
          <CardContent className="p-2">
            <div className="max-h-60 overflow-y-auto space-y-1">
              {results.map((result, index) => (
                <button
                  key={result.place_id}
                  onClick={() => handleResultSelect(result)}
                  className={`w-full text-left p-2 rounded-sm flex items-start gap-2 text-sm transition-colors
                             ${index === selectedIndex 
                               ? 'bg-primary text-primary-foreground' 
                               : 'hover:bg-muted'
                             }`}
                >
                  <MapPin className="w-4 h-4 mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">
                      {result.display_name.split(',')[0]}
                    </p>
                    <p className="text-xs opacity-70 truncate">
                      {result.display_name.split(',').slice(1).join(',').trim()}
                    </p>
                  </div>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {showResults && results.length === 0 && !loading && query.length >= 3 && (
        <Card className="absolute top-full left-0 right-0 z-50 mt-1">
          <CardContent className="p-4 text-center text-muted-foreground">
            No locations found for &quot;{query}&quot;
          </CardContent>
        </Card>
      )}
    </div>
  );
}