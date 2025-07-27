'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Search, MapPin, Loader2 } from 'lucide-react';

interface AddressResult {
  display_name: string;
  lat: number;
  lng: number;
  place_id: string;
  importance: number;
}

interface AddressSearchProps {
  placeholder?: string;
  onAddressSelect: (address: AddressResult) => void;
  value?: string;
  className?: string;
}

export default function AddressSearch({ 
  placeholder = "Search for an address...", 
  onAddressSelect, 
  value = "",
  className = ""
}: AddressSearchProps) {
  const [query, setQuery] = useState(value);
  const [results, setResults] = useState<AddressResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  
  const searchRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Debounced search function
  const searchAddresses = async (searchQuery: string) => {
    if (searchQuery.length < 3) {
      setResults([]);
      setShowDropdown(false);
      return;
    }

    setIsLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/search-addresses', {
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
          setShowDropdown(data.results.length > 0);
        }
      }
    } catch (error) {
      console.error('Address search error:', error);
      setResults([]);
    } finally {
      setIsLoading(false);
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

  // Handle keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!showDropdown || results.length === 0) return;

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
          handleAddressSelect(results[selectedIndex]);
        }
        break;
      case 'Escape':
        setShowDropdown(false);
        setSelectedIndex(-1);
        inputRef.current?.blur();
        break;
    }
  };

  // Handle address selection
  const handleAddressSelect = (address: AddressResult) => {
    setQuery(address.display_name);
    setShowDropdown(false);
    setSelectedIndex(-1);
    onAddressSelect(address);
  };

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setShowDropdown(false);
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
    <div ref={searchRef} className={`relative ${className}`}>
      <div className="relative">
        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
          {isLoading ? (
            <Loader2 className="h-4 w-4 text-gray-400 animate-spin" />
          ) : (
            <Search className="h-4 w-4 text-gray-400" />
          )}
        </div>
        
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (results.length > 0) {
              setShowDropdown(true);
            }
          }}
          placeholder={placeholder}
          className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg 
                     focus:ring-2 focus:ring-blue-500 focus:border-transparent 
                     bg-white text-gray-900 placeholder-gray-500
                     transition-all duration-200"
        />
      </div>

      {/* Dropdown */}
      {showDropdown && results.length > 0 && (
        <div className="absolute z-50 w-full mt-1 bg-white border border-gray-200 
                        rounded-lg shadow-lg max-h-60 overflow-y-auto">
          {results.map((result, index) => (
            <div
              key={result.place_id}
              onClick={() => handleAddressSelect(result)}
              className={`px-4 py-3 cursor-pointer transition-colors duration-150
                         ${index === selectedIndex 
                           ? 'bg-blue-50 border-l-4 border-blue-500' 
                           : 'hover:bg-gray-50'
                         }
                         ${index === 0 ? 'rounded-t-lg' : ''}
                         ${index === results.length - 1 ? 'rounded-b-lg' : 'border-b border-gray-100'}
                       `}
            >
              <div className="flex items-start space-x-3">
                <MapPin className="h-4 w-4 text-gray-400 mt-0.5 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">
                    {result.display_name.split(',')[0]}
                  </p>
                  <p className="text-xs text-gray-500 truncate">
                    {result.display_name.split(',').slice(1).join(',').trim()}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* No results message */}
      {showDropdown && results.length === 0 && !isLoading && query.length >= 3 && (
        <div className="absolute z-50 w-full mt-1 bg-white border border-gray-200 
                        rounded-lg shadow-lg p-4">
          <div className="flex items-center space-x-3 text-gray-500">
            <Search className="h-4 w-4" />
            <span className="text-sm">No addresses found for &quot;{query}&quot;</span>
          </div>
        </div>
      )}
    </div>
  );
}