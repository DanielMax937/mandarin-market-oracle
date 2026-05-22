// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title ReasoningRegistry
/// @notice Minimal provenance registry for research prediction-market recommendations.
/// @dev Stores hashes only. No funds are held and no trading is performed.
contract ReasoningRegistry {
    event RecommendationRecorded(
        bytes32 indexed recommendationHash,
        bytes32 indexed evidenceHash,
        string marketSlug,
        string signalId,
        string direction,
        uint256 marketProbabilityBps,
        uint256 agentProbabilityBps,
        uint256 riskUnitSize,
        address indexed recorder
    );

    mapping(bytes32 => bool) public recorded;

    function recordRecommendation(
        bytes32 recommendationHash,
        bytes32 evidenceHash,
        string calldata marketSlug,
        string calldata signalId,
        string calldata direction,
        uint256 marketProbabilityBps,
        uint256 agentProbabilityBps,
        uint256 riskUnitSize
    ) external {
        require(recommendationHash != bytes32(0), "recommendation hash required");
        require(evidenceHash != bytes32(0), "evidence hash required");
        require(!recorded[recommendationHash], "already recorded");

        recorded[recommendationHash] = true;

        emit RecommendationRecorded(
            recommendationHash,
            evidenceHash,
            marketSlug,
            signalId,
            direction,
            marketProbabilityBps,
            agentProbabilityBps,
            riskUnitSize,
            msg.sender
        );
    }
}
